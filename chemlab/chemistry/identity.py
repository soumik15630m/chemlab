from __future__ import annotations

from rdkit import Chem

from chemlab.records import Molecule, MoleculeError, MoleculeResult, Status


def identify(smiles: str) -> MoleculeResult:
    if not isinstance(smiles, str) or not smiles.strip():
        return MoleculeError(
            status="parse_error", original_smiles=str(smiles), error="Empty SMILES"
        )
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None or mol.GetNumAtoms() == 0:
            raise ValueError("RDKit could not parse and sanitize the molecule")
        if any(a.HasQuery() or a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
            return MoleculeError(
                status="unsupported_input",
                original_smiles=smiles,
                error="Query atoms and wildcard atoms are unsupported",
            )
        # Enhanced stereo and CX metadata need their own identity policy before admission.
        if mol.GetStereoGroups() or "|" in smiles:
            return MoleculeError(
                status="unsupported_input",
                original_smiles=smiles,
                error="CXSMILES/enhanced stereo is outside identity-v1 scope",
            )
        mapped = smiles if any(a.GetAtomMapNum() for a in mol.GetAtoms()) else None
        for atom in mol.GetAtoms():
            atom.SetAtomMapNum(0)
        Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
        stereo = list(Chem.FindPotentialStereo(mol))
        return Molecule(
            original_smiles=smiles,
            canonical_smiles=Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True),
            mapped_smiles=mapped,
            unspecified_stereo=any(str(s.specified) == "Unspecified" for s in stereo),
            specified_stereo=any(str(s.specified) == "Specified" for s in stereo),
        )
    except Exception as exc:
        return MoleculeError(status="parse_error", original_smiles=smiles, error=str(exc))


def require_molecule(smiles: str) -> Molecule:
    result = identify(smiles)
    if isinstance(result, MoleculeError):
        raise ValueError(f"{result.status}: {result.error}: {smiles}")
    return result


def require_stable_molecule(smiles: str) -> Molecule:
    result = require_molecule(smiles)
    if require_molecule(result.canonical_smiles).canonical_smiles != result.canonical_smiles:
        raise ValueError("identity_v1_not_idempotent_under_pinned_rdkit")
    return result


def stereo_relation(left: str, right: str) -> str:
    a, b = require_stable_molecule(left), require_stable_molecule(right)
    if a.canonical_smiles == b.canonical_smiles:
        return "exact"
    am, bm = Chem.MolFromSmiles(a.canonical_smiles), Chem.MolFromSmiles(b.canonical_smiles)
    aa, bb = Chem.Mol(am), Chem.Mol(bm)
    Chem.RemoveStereochemistry(aa)
    Chem.RemoveStereochemistry(bb)
    if Chem.MolToSmiles(aa) != Chem.MolToSmiles(bb):
        return "different"
    # Enumerating unspecified centers preserves jointly specified constraints.
    from rdkit.Chem.EnumerateStereoisomers import (
        EnumerateStereoisomers,
        StereoEnumerationOptions,
    )

    if not (a.unspecified_stereo or b.unspecified_stereo):
        return "different"
    if (
        max(
            sum(str(s.specified) == "Unspecified" for s in Chem.FindPotentialStereo(m))
            for m in (am, bm)
        )
        > 10
    ):
        return "indeterminate"
    options = StereoEnumerationOptions(onlyUnassigned=True, unique=True, maxIsomers=1024)
    aset = {Chem.MolToSmiles(m, isomericSmiles=True) for m in EnumerateStereoisomers(am, options)}
    bset = {Chem.MolToSmiles(m, isomericSmiles=True) for m in EnumerateStereoisomers(bm, options)}
    return "compatible_missing_stereo" if aset & bset else "different"


def mapping_status(mapped_reaction: str | None) -> tuple[Status, str]:
    if not mapped_reaction:
        return "unknown", "mapping_missing"
    try:
        left, right = mapped_reaction.split(">>")
        sides = [Chem.MolFromSmiles(s) for s in (left, right)]
        if any(m is None for m in sides):
            return "fail", "mapping_parse_failure"
        maps = []
        for mol in sides:
            numbers = [a.GetAtomMapNum() for a in mol.GetAtoms() if a.GetAtomMapNum()]
            if len(numbers) != len(set(numbers)):
                return "fail", "duplicate_map_number"
            maps.append(
                {
                    a.GetAtomMapNum(): (a.GetAtomicNum(), a.GetIsotope())
                    for a in mol.GetAtoms()
                    if a.GetAtomMapNum()
                }
            )
        incomplete = False
        for atom in sides[1].GetAtoms():
            number = atom.GetAtomMapNum()
            if not number or number not in maps[0]:
                incomplete = True
                continue
            if maps[0][number] != maps[1][number]:
                return "fail", "mapped_element_or_isotope_mismatch"
        if incomplete:
            return "unknown", "product_atom_provenance_missing"
        return "pass", "mapped_product_atoms_have_provenance"
    except Exception:
        return "fail", "invalid_mapping_representation"
