"""Read-only reaction observations; never an engine acceptance decision."""

from __future__ import annotations

from collections import Counter
from typing import Any

from rdkit import Chem, rdBase
from rdkit.Chem.MolStandardize import rdMolStandardize

from chemlab.chemistry import require_molecule
from chemlab.chemistry.identity import mapping_status
from chemlab.records import Candidate, ForwardEvidence, Molecule, Prediction, digest
from chemlab.reporting.formats import selected_route
from chemlab.store import IntegrityError

VERSION = "reaction-observations-v2"
LIMITATION = (
    "Observations describe represented inputs, not chemical feasibility. "
    "Missing reagents, stoichiometry, conditions and by-products limit interpretation. "
    "No observation changes identity-v1, frozen forward evidence or search decisions."
)


def _molecule(smiles: str):
    identity = require_molecule(smiles)
    return Chem.MolFromSmiles(identity.canonical_smiles)


def atom_inventory(product: str, precursors: tuple[str, ...]) -> dict[str, Any]:
    try:
        if not precursors:
            raise ValueError("At least one listed precursor is required")

        def inventory(smiles):
            mol = _molecule(smiles)
            return Counter(
                (a.GetSymbol(), a.GetIsotope())
                for a in mol.GetAtoms()
                if a.GetAtomicNum() > 1 or a.GetIsotope()
            )

        left: Counter = Counter()
        for smiles in precursors:
            left.update(inventory(smiles))
        right = inventory(product)
        elements = {symbol for symbol, _ in left}
        missing = sorted({symbol for symbol, _ in right if symbol != "H"} - elements)
        isotopes = sorted(
            (symbol, isotope)
            for symbol, isotope in right
            if isotope and not left[(symbol, isotope)]
        )
        return {
            "status": "observed",
            "counts": [
                {
                    "element": symbol,
                    "isotope": isotope,
                    "listed_precursors": left[(symbol, isotope)],
                    "product": right[(symbol, isotope)],
                }
                for symbol, isotope in sorted(left.keys() | right.keys())
            ],
            "elements_without_listed_source": missing,
            "isotope_labels_without_listed_source": [list(key) for key in isotopes],
            "count_basis": (
                "Heavy atoms and explicit hydrogen isotope labels per occurrence; "
                "not stoichiometric coefficients"
            ),
            "interpretation": (
                "Absent listed sources need investigation; "
                "counts do not certify atom balance or chemistry"
            ),
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


def mapped_edits(product: str, precursors: tuple[str, ...], mapped: str | None) -> dict[str, Any]:
    status, reason = mapping_status(mapped)
    if status != "pass":
        return {"status": "unknown", "reason": reason, "mapping_status": status}
    try:
        assert mapped is not None
        left, right = mapped.split(">>")
        if (
            require_molecule(left).canonical_smiles
            != require_molecule(".".join(precursors)).canonical_smiles
            or require_molecule(right).canonical_smiles
            != require_molecule(product).canonical_smiles
        ):
            return {"status": "unknown", "reason": "mapping_reaction_identity_mismatch"}
        reactants, output = Chem.MolFromSmiles(left), Chem.MolFromSmiles(right)
        if any(a.GetAtomicNum() == 1 for m in (reactants, output) for a in m.GetAtoms()):
            return {
                "status": "unknown",
                "reason": "explicit_hydrogen_mapping_outside_diagnostic_scope",
            }
        if any(not a.GetAtomMapNum() for m in (reactants, output) for a in m.GetAtoms()):
            return {
                "status": "unknown",
                "reason": "unmapped_atoms_prevent_complete_edit_observation",
            }

        def atoms(mol):
            return {a.GetAtomMapNum(): a for a in mol.GetAtoms()}

        def bonds(mol):
            return {
                tuple(
                    sorted((b.GetBeginAtom().GetAtomMapNum(), b.GetEndAtom().GetAtomMapNum()))
                ): str(b.GetBondType())
                for b in mol.GetBonds()
            }

        before, after = bonds(reactants), bonds(output)
        la, ra = atoms(reactants), atoms(output)
        return {
            "status": "observed",
            "appeared_in_product": [
                {"maps": list(key), "order": after[key]}
                for key in sorted(after.keys() - before.keys())
            ],
            "absent_from_product": [
                {"maps": list(key), "order": before[key]}
                for key in sorted(before.keys() - after.keys())
            ],
            "order_changed": [
                {"maps": list(key), "before": before[key], "after": after[key]}
                for key in sorted(before.keys() & after.keys())
                if before[key] != after[key]
            ],
            "reactant_maps_absent_from_product": sorted(la.keys() - ra.keys()),
            "formal_charge_changes": [
                {
                    "map": number,
                    "before": la[number].GetFormalCharge(),
                    "after": ra[number].GetFormalCharge(),
                }
                for number in sorted(ra)
                if la[number].GetFormalCharge() != ra[number].GetFormalCharge()
            ],
            "interpretation": (
                "Changes under supplied mapping, not a validated mechanism; "
                "absent atoms may enter unlisted by-products"
            ),
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


def representation_diagnostic(
    product: str, outputs: tuple[str, ...], *, max_tautomers: int = 128, max_transforms: int = 256
) -> dict[str, Any]:
    settings = {
        "max_tautomers": max_tautomers,
        "max_transforms": max_transforms,
        "remove_bond_stereo": False,
        "remove_sp3_stereo": False,
    }
    try:
        if max_tautomers < 1 or max_transforms < 1:
            raise ValueError("Enumeration bounds must be positive")
        if not outputs:
            return {"status": "unknown", "reason": "no_forward_products", "settings": settings}
        identities = [require_molecule(s) for s in (product, *outputs)]
        enumerator = rdMolStandardize.TautomerEnumerator()
        enumerator.SetMaxTautomers(max_tautomers)
        enumerator.SetMaxTransforms(max_transforms)
        enumerator.SetRemoveBondStereo(False)
        enumerator.SetRemoveSp3Stereo(False)

        def family(identity):
            mol = _molecule(identity.canonical_smiles)
            if identity.specified_stereo or any(a.GetIsotope() for a in mol.GetAtoms()):
                return None, "specified_stereo_or_isotopes_outside_tautomer_diagnostic_scope"
            result = enumerator.Enumerate(mol)
            if str(result.status) != "Completed":
                return None, "tautomer_enumeration_incomplete"
            return Chem.MolToSmiles(enumerator.PickCanonical(result), isomericSmiles=True), None

        expected, expected_reason = family(identities[0])
        comparisons = []
        for rank, identity in enumerate(identities[1:], 1):
            if identity.canonical_smiles == identities[0].canonical_smiles:
                comparisons.append({"rank": rank, "relation": "exact_identity"})
                continue
            value, reason = family(identity)
            if expected is None or value is None:
                comparisons.append(
                    {"rank": rank, "relation": "unknown", "reason": expected_reason or reason}
                )
            else:
                comparisons.append(
                    {
                        "rank": rank,
                        "relation": "shared_enumerated_tautomer"
                        if expected == value
                        else "different_enumerated_tautomer",
                    }
                )
        return {
            "status": "observed",
            "comparisons": comparisons,
            "settings": settings,
            "interpretation": (
                "Diagnostic representation overlap only; "
                "exact identity and frozen forward results remain unchanged"
            ),
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "settings": settings}


def _payload(objects: dict, ref: str, kind: str) -> Any:
    envelope = objects.get(ref)
    if envelope is None or digest(envelope) != ref or envelope.get("kind") != kind:
        raise IntegrityError(f"Missing, corrupt or wrong-kind diagnostic input: {ref}")
    return envelope["payload"]


def diagnose_route(bundle: dict[str, Any], route_ref: str) -> dict[str, Any]:
    objects = bundle["objects"]
    items = [
        item
        for group in bundle["groups"].values()
        for item in group
        if item["route_ref"] == route_ref
    ]
    if not items:
        raise KeyError(route_ref)
    if len(items) != 1:
        raise IntegrityError("Diagnostic route membership is ambiguous")
    _payload(objects, route_ref, "route")
    route, report = selected_route(bundle, route_ref)
    item = items[0]
    _payload(objects, item["report_ref"], "verification_report")
    nodes = {node.id: node.molecule.canonical_smiles for node in route.molecules}
    steps = []
    for step in route.steps:
        prediction = Prediction.model_validate(_payload(objects, step.prediction_ref, "prediction"))
        candidates = [c for c in prediction.candidates if c.index == step.candidate_index]
        if (
            prediction.status != "ok"
            or len(candidates) != 1
            or not isinstance(candidates[0], Candidate)
        ):
            raise IntegrityError("Diagnostic step has no successful bound candidate")
        candidate = candidates[0]
        product = candidate.product.canonical_smiles
        precursors = tuple(m.canonical_smiles for m in candidate.precursors)
        if product != nodes[step.product_id] or set(precursors) != {
            nodes[mid] for mid in step.precursor_ids
        }:
            raise IntegrityError("Diagnostic candidate differs from exported transformation")
        checks = [c for c in report.checks if c.name == f"forward:{step.id}"]
        forward: dict[str, Any] = {
            "status": "unknown",
            "reason": "no_complete_bound_forward_output",
        }
        forward_refs = []
        if len(checks) == 1 and len(checks[0].evidence) == 1:
            ref = checks[0].evidence[0]
            evidence = ForwardEvidence.model_validate(_payload(objects, ref, "forward_evidence"))
            forward_refs.append(ref)
            check = checks[0]
            if (
                check.inputs.get("product") != product
                or check.inputs.get("precursors") != list(precursors)
                or evidence.requested_count != check.inputs.get("k")
                or evidence.manifest_ref != check.settings.get("manifest_ref")
            ):
                raise IntegrityError("Diagnostic forward evidence binding mismatch")
            if (
                evidence.status == "ok"
                and not evidence.information_lost
                and all(isinstance(m, Molecule) for m in evidence.products)
            ):
                if (
                    evidence.effective_input
                    != require_molecule(".".join(precursors)).canonical_smiles
                ):
                    raise IntegrityError("Diagnostic forward effective input mismatch")
                forward = representation_diagnostic(
                    product,
                    tuple(m.canonical_smiles for m in evidence.products if isinstance(m, Molecule)),
                )
        steps.append(
            {
                "step_id": step.id,
                "prediction_ref": step.prediction_ref,
                "candidate_index": step.candidate_index,
                "forward_refs": forward_refs,
                "product": product,
                "precursors": list(precursors),
                "chemical_assessment": "unresolved",
                "atom_inventory": atom_inventory(product, precursors),
                "mapped_edits": mapped_edits(product, precursors, candidate.mapped_reaction),
                "forward_representation": forward,
                "recorded_forward_status": checks[0].status if len(checks) == 1 else "not_checked",
                "recorded_precedent": report.precedent.get(step.id, {}),
            }
        )
    return {
        "version": VERSION,
        "rdkit_version": rdBase.rdkitVersion,
        "mode": "read_only_observations",
        "route_ref": route_ref,
        "target": report.target,
        "report_ref": item["report_ref"],
        "chemical_assessment": "unresolved" if steps else "not_applicable",
        "recorded_structural_status": report.structural_status,
        "recorded_forward_status": report.forward_status,
        "steps": steps,
        "limitation": LIMITATION,
    }
