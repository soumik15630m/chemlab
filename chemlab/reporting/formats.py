"""Structure-preserving exports of published, structurally verified routes."""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections import Counter
from typing import Any

from rdkit import Chem
from rdkit.Chem import rdChemReactions, rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

from chemlab.chemistry import require_molecule
from chemlab.records import Route, VerificationReport, canonical_bytes, digest
from chemlab.store import IntegrityError


def depiction_molecule(smiles: str):
    identity = require_molecule(smiles)
    mol = Chem.MolFromSmiles(identity.canonical_smiles)
    rdDepictor.Compute2DCoords(mol, canonOrient=True, clearConfs=True, sampleSeed=0)
    return mol


def molecule_identity(mol) -> str:
    if mol is None:
        raise IntegrityError("Export could not be reimported")
    return require_molecule(Chem.MolToSmiles(mol, isomericSmiles=True)).canonical_smiles


def molecule_mol(smiles: str) -> bytes:
    mol = depiction_molecule(smiles)
    block = Chem.MolToV3KMolBlock(mol)
    restored = Chem.MolFromMolBlock(block, sanitize=True, removeHs=False)
    if molecule_identity(restored) != require_molecule(smiles).canonical_smiles:
        raise IntegrityError("MOL export changed molecular identity")
    return block.encode("ascii")


def molecule_image(smiles: str) -> bytes:
    drawer = rdMolDraw2D.MolDraw2DCairo(1200, 360)
    drawer.DrawMolecule(depiction_molecule(smiles))
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def selected_route(bundle: dict[str, Any], route_ref: str) -> tuple[Route, VerificationReport]:
    for items in bundle["groups"].values():
        for item in items:
            if item["route_ref"] == route_ref:
                route = Route.model_validate(bundle["objects"][route_ref]["payload"])
                report = VerificationReport.model_validate(
                    bundle["objects"][item["report_ref"]]["payload"]
                )
                if report.route_hash != digest(route):
                    raise IntegrityError("Export report is bound to another route")
                if report.structural_status != "verified":
                    raise ValueError(
                        "Editable chemistry exports require a structurally verified route"
                    )
                return route, report
    raise KeyError(route_ref)


def reaction_for_step(route: Route, step):
    molecules = {m.id: m.molecule.canonical_smiles for m in route.molecules}
    reaction = rdChemReactions.ChemicalReaction()
    for occurrence in step.precursor_ids:
        reaction.AddReactantTemplate(depiction_molecule(molecules[occurrence]))
    reaction.AddProductTemplate(depiction_molecule(molecules[step.product_id]))
    return reaction


def reaction_participants(reaction) -> tuple[Counter, Counter]:
    if reaction is None:
        raise IntegrityError("Reaction export could not be reimported")
    return (
        Counter(molecule_identity(m) for m in reaction.GetReactants()),
        Counter(molecule_identity(m) for m in reaction.GetProducts()),
    )


def step_files(route: Route, step) -> tuple[bytes, str]:
    reaction = reaction_for_step(route, step)
    molecules = {m.id: m.molecule.canonical_smiles for m in route.molecules}
    expected = (
        Counter(molecules[mid] for mid in step.precursor_ids),
        Counter({molecules[step.product_id]: 1}),
    )
    rxn = rdChemReactions.ReactionToV3KRxnBlock(reaction)
    restored = rdChemReactions.ReactionFromRxnBlock(rxn, sanitize=True, removeHs=False)
    if reaction_participants(restored) != expected:
        raise IntegrityError("RXN export changed reaction participants")
    smiles = rdChemReactions.ReactionToSmiles(reaction, canonical=True)
    parsed = rdChemReactions.ReactionFromSmarts(smiles, useSmiles=True)
    if reaction_participants(parsed) != expected:
        raise IntegrityError("Reaction SMILES export changed reaction participants")
    return rxn.encode("ascii"), smiles


def reaction_image(route: Route, step, *, svg: bool = False) -> bytes:
    reaction = reaction_for_step(route, step)
    drawer = rdMolDraw2D.MolDraw2DSVG(1440, 380) if svg else rdMolDraw2D.MolDraw2DCairo(1440, 380)
    drawer.DrawReaction(reaction)
    drawer.FinishDrawing()
    result = drawer.GetDrawingText()
    return result.encode("utf-8") if isinstance(result, str) else result


def chemistry_zip(bundle: dict[str, Any], route_ref: str) -> bytes:
    route, report = selected_route(bundle, route_ref)
    files = {
        "route.json": canonical_bytes(route),
        "verification-report.json": canonical_bytes(report),
    }
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "run_id": bundle["run_id"],
        "route_ref": route_ref,
        "identity_policy": "identity-v1",
        "verification_policy": report.policy,
        "structural_status": report.structural_status,
        "forward_status": report.forward_status,
        "coordinates": "deterministic 2D depictions; not optimized 3D geometries",
        "reaction_direction": "precursors_to_product",
        "molecules": [],
        "steps": [],
        "limitations": (
            "No invented conditions, atom mapping, stoichiometry or experimental guarantee"
        ),
    }
    stream = io.StringIO()
    writer = Chem.SDWriter(stream)
    writer.SetForceV3000(True)
    smiles_lines = []
    for index, occurrence in enumerate(route.molecules, start=1):
        name = f"molecules/molecule-{index:04d}.mol"
        smiles = occurrence.molecule.canonical_smiles
        files[name] = molecule_mol(smiles)
        mol = Chem.MolFromMolBlock(files[name].decode("ascii"), sanitize=True, removeHs=False)
        mol.SetProp("_Name", occurrence.id)
        mol.SetProp("occurrence_id", occurrence.id)
        mol.SetProp("canonical_smiles", smiles)
        mol.SetProp("route_ref", route_ref)
        mol.SetProp("structural_status", report.structural_status)
        mol.SetProp("forward_status", report.forward_status)
        writer.write(mol)
        smiles_lines.append(f"{smiles}\t{occurrence.id}")
        metadata["molecules"].append({"occurrence_id": occurrence.id, "file": name})
    writer.flush()
    files["molecules.sdf"] = stream.getvalue().encode("ascii")
    writer.close()
    restored = list(Chem.ForwardSDMolSupplier(io.BytesIO(files["molecules.sdf"]), removeHs=False))
    if [molecule_identity(m) for m in restored] != [
        m.molecule.canonical_smiles for m in route.molecules
    ]:
        raise IntegrityError("SDF export changed molecular occurrences")
    files["molecules.smi"] = ("\n".join(smiles_lines) + "\n").encode("ascii")
    reactions = []
    for index, step in enumerate(route.steps, start=1):
        name = f"reactions/step-{index:04d}.rxn"
        files[name], smiles = step_files(route, step)
        files[name.replace(".rxn", ".svg")] = reaction_image(route, step, svg=True)
        reactions.append(f"{smiles}\t{step.id}")
        metadata["steps"].append(
            {
                "step_id": step.id,
                "file": name,
                "product_id": step.product_id,
                "precursor_ids": list(step.precursor_ids),
                "reaction_smiles": smiles,
            }
        )
    files["reactions.smi"] = ("\n".join(reactions) + ("\n" if reactions else "")).encode("ascii")
    metadata["files"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())
    }
    files["manifest.json"] = canonical_bytes(metadata)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output.getvalue()
