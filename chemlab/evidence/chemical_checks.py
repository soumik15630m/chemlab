"""Explicit reaction evidence obligations; no experimental feasibility oracle."""

from __future__ import annotations

from typing import Any

from chemlab.chemistry.identity import mapping_status
from chemlab.evidence.reaction_diagnostics import atom_inventory, mapped_edits
from chemlab.evidence.reaction_library import ReactionLibrary, reaction_input
from chemlab.evidence.reaction_templates import ContextLibrary
from chemlab.records import digest

POLICY: dict[str, Any] = {
    "version": "reaction-evidence-obligations-v1",
    "identity": "identity-v1",
    "atom_origin": "Heavy elements and explicitly labelled isotopes require a listed source",
    "stoichiometry": "Unknown; counts alone cannot reject when coefficients are absent",
    "mapping": "Auxiliary; require exact complete input binding and valid atom provenance",
    "precedent": "Exact full identities and precursor occurrences; no missing-match rejection",
    "contexts": "RDChiral source context plus exact precursor replay; analogy only",
    "source_limit": 100,
    "dependency_timeout_seconds": 10,
    "conditions": "Excluded; contextual feasibility and selectivity remain unresolved",
    "acceptance": "Observation only; existing structural and forward contracts unchanged",
}


def validate_mapping(query: dict, proposal: dict | None) -> dict:
    if proposal is None:
        return {"status": "unknown", "reason": "mapping_missing"}
    try:
        if proposal["input_key"] != digest(query) or proposal["input"] != query:
            return {"status": "fail", "reason": "mapping_input_binding_mismatch"}
        if proposal["status"] != "ok":
            return {"status": "error", "reason": "mapping_provider_error"}
        mapped = proposal["raw_prediction"]["mapped_rxn"]
        left, right = mapped.split(">>")
        if reaction_input(right, tuple(left.split("."))) != query:
            return {"status": "fail", "reason": "mapped_reaction_identity_mismatch"}
        status, reason = mapping_status(mapped)
        return {
            "status": status,
            "reason": reason,
            "mapped_reaction": mapped,
            "proposal_hash": digest(proposal),
        }
    except Exception as exc:
        return {"status": "error", "reason": "unreadable_mapping_proposal", "error": str(exc)}


def assess_reaction(
    product: str,
    precursors: tuple[str, ...],
    *,
    proposal: dict | None = None,
    library: ReactionLibrary | None = None,
    contexts: ContextLibrary | None = None,
    excluded: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    query = reaction_input(product, precursors)
    inventory = atom_inventory(query["product"], tuple(query["precursors"]))
    mapping = validate_mapping(query, proposal)
    checks: dict[str, Any] = {
        "atom_origin": inventory,
        "mapping": mapping,
        "conditions": {"status": "not_checked", "reason": "outside_requested_scope"},
        "stoichiometry": {
            "status": "unknown",
            "reason": "coefficients_and_byproducts_not_supplied",
        },
        "contextual_feasibility": {
            "status": "unknown",
            "reason": "no_complete_condition_free_chemical_oracle",
        },
    }
    contradiction = bool(
        inventory.get("elements_without_listed_source")
        or inventory.get(
            "isotope_labels_without_listed_source",
        )
    )
    checks["listed_atom_sources"] = {
        "status": "fail"
        if contradiction
        else "pass"
        if inventory["status"] == "observed"
        else "error",
        "reason": "listed_atom_source_missing"
        if contradiction
        else "listed_element_sources_present",
        "scope": "Represented inputs only; omitted reagents can change this assessment",
    }
    checks["edits"] = mapped_edits(
        query["product"],
        tuple(query["precursors"]),
        mapping.get("mapped_reaction") if mapping["status"] == "pass" else None,
    )
    for name in ("exact_precedent", "context_precedent"):
        checks[name] = {"status": "not_checked", "reason": "knowledge_library_not_configured"}
    try:
        if library is not None:
            checks["exact_precedent"] = library.lookup(
                query["product"],
                tuple(query["precursors"]),
                excluded=excluded,
                limit=POLICY["source_limit"],
            )
    except Exception as exc:
        checks["exact_precedent"] = {"status": "error", "reason": str(exc)}
    try:
        if contexts is not None:
            if mapping["status"] == "pass":
                checks["context_precedent"] = contexts.lookup(
                    mapping["mapped_reaction"],
                    query["product"],
                    tuple(query["precursors"]),
                    excluded=excluded,
                    limit=POLICY["source_limit"],
                )
            else:
                checks["context_precedent"] = {
                    "status": "unknown",
                    "reason": "validated_mapping_required",
                }
    except Exception as exc:
        checks["context_precedent"] = {"status": "error", "reason": str(exc)}
    support = any(
        checks[name]["status"] in ("reported_match", "context_replay_match")
        for name in (
            "exact_precedent",
            "context_precedent",
        )
    )
    errors = any(check.get("status") == "error" for check in checks.values())
    outcome = (
        "contradiction"
        if contradiction
        else "error"
        if errors
        else "support"
        if support
        else "unresolved"
    )
    return {
        "input": query,
        "input_key": digest(query),
        "policy": POLICY,
        "policy_hash": digest(POLICY),
        "checks": checks,
        "evidence_outcome": outcome,
        "chemical_feasibility": "unresolved",
        "interpretation": (
            "Support means reported precedent or source-derived structural analogy. "
            "Contradiction concerns represented atom-source obligations, "
            "not universal infeasibility. Missing precedent is not a failed reaction; "
            "mapping errors cannot supply edit evidence."
        ),
    }
