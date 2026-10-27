from __future__ import annotations

from collections import Counter
from typing import Any

from rdchiral.main import rdchiralRunText

from chemlab.adapters.models import ModelService, score_cost
from chemlab.chemistry import require_molecule
from chemlab.chemistry.identity import mapping_status
from chemlab.evidence.checks import forward_check, load_stock, precedent_lookup
from chemlab.records import (
    Candidate,
    Check,
    ForwardStatus,
    ModelManifest,
    Prediction,
    Route,
    RunConfig,
    Status,
    StructuralStatus,
    VerificationReport,
    digest,
)
from chemlab.store import IntegrityError, Store


def disposition(checks: list[Check]) -> StructuralStatus:
    mandatory = [c for c in checks if c.mandatory]
    if any(c.status == "fail" for c in mandatory):
        return "rejected"
    if any(c.status not in ("pass", "not_applicable") for c in mandatory):
        return "unresolved"
    return "verified"


def verify(
    store: Store,
    serialized: Any,
    target: str,
    config: RunConfig,
    forward: ModelService | None = None,
) -> VerificationReport:
    try:
        route_hash = digest(serialized)
    except (TypeError, ValueError) as exc:
        return VerificationReport(
            route_hash=digest({"invalid_source_representation": repr(serialized)}),
            target=target,
            stock_ref=config.stock_ref,
            mapping_profile=config.mapping_profile,
            structural_status="rejected",
            forward_status="incomplete",
            checks=(Check(name="schema", status="fail", reason=f"noncanonical_input: {exc}"),),
            mapping_coverage={"checked": 0, "missing": 0, "failed": 0},
            precedent={"status": "not_checked"},
        )
    checks: list[Check] = []
    candidates: dict[str, Candidate] = {}
    templates: dict[str, str | None] = {}
    precedent: dict[str, Any] = {}
    coverage = Counter({"checked": 0, "missing": 0, "failed": 0})

    def add(name: str, status: Status, reason: str, **kwargs):
        checks.append(
            Check(
                name=name,
                status=status,
                reason=reason,
                inputs={"route_hash": route_hash, **kwargs.pop("inputs", {})},
                **kwargs,
            )
        )

    def report() -> VerificationReport:
        structural = disposition(checks)
        forward_status: ForwardStatus
        forward_checks = [c for c in checks if c.name.startswith("forward:")]
        if not route.steps:
            forward_status = "not_applicable"
        elif any(c.status == "fail" for c in forward_checks):
            forward_status = "conflict"
        elif len(forward_checks) == len(route.steps) and all(
            c.status == "pass" for c in forward_checks
        ):
            forward_status = "consistent"
        else:
            forward_status = "incomplete"
        return VerificationReport(
            route_hash=route_hash,
            target=target,
            stock_ref=config.stock_ref,
            mapping_profile=config.mapping_profile,
            structural_status=structural,
            forward_status=forward_status,
            checks=tuple(checks),
            mapping_coverage=dict(coverage),
            precedent=precedent if route.steps else {"status": "not_applicable"},
        )

    try:
        route = Route.model_validate(serialized)
        target = require_molecule(target).canonical_smiles
        add("schema", "pass", "route_schema_valid")
    except Exception as exc:
        return VerificationReport(
            route_hash=route_hash,
            target=target,
            stock_ref=config.stock_ref,
            mapping_profile=config.mapping_profile,
            structural_status="rejected",
            forward_status="incomplete",
            checks=(Check(name="schema", status="fail", reason=str(exc)),),
            mapping_coverage=dict(coverage),
            precedent={"status": "not_checked"},
        )
    nodes = {m.id: m for m in route.molecules}
    steps = {s.product_id: s for s in route.steps}
    identities: dict[str, str] = {}
    try:
        if len(nodes) != len(route.molecules) or len(steps) != len(route.steps):
            raise ValueError("Duplicate occurrence ID or multiple selected reactions")
        if len({s.id for s in route.steps}) != len(route.steps) or set(nodes) & {
            s.id for s in route.steps
        }:
            raise ValueError(
                "Reaction occurrence IDs must be unique and disjoint from molecule IDs"
            )
        if route.root_id not in nodes:
            raise ValueError("Missing root occurrence")
        for node in route.molecules:
            reconstructed = require_molecule(node.molecule.original_smiles)
            if reconstructed != node.molecule:
                raise ValueError(f"Serialized molecular identity/flags mismatch: {node.id}")
            identities[node.id] = reconstructed.canonical_smiles
        if identities[route.root_id] != target:
            raise ValueError("Root does not match requested target")
        add("identity", "pass", "serialized_molecules_reconstructed")
    except Exception as exc:
        add("identity", "fail", str(exc))
        return report()
    try:
        parents: Counter[str] = Counter()
        for step in route.steps:
            if step.product_id not in nodes or any(p not in nodes for p in step.precursor_ids):
                raise ValueError("Reaction refers to an absent occurrence")
            parents.update(step.precursor_ids)
        if parents[route.root_id] or any(
            parents[mid] != 1 for mid in nodes if mid != route.root_id
        ):
            raise ValueError("Root/parent counts violate occurrence-tree contract")
        reached: set[str] = set()

        def visit(mid: str, ancestors: frozenset[str]):
            if mid in reached or identities[mid] in ancestors:
                raise ValueError("Shared occurrence or molecular ancestor recurrence")
            reached.add(mid)
            step = steps.get(mid)
            if step:
                for child in step.precursor_ids:
                    visit(child, ancestors | {identities[mid]})

        visit(route.root_id, frozenset())
        if reached != set(nodes):
            raise ValueError("Extraneous or unreachable branch")
        add("graph", "pass", "complete_acyclic_occurrence_tree")
    except Exception as exc:
        add("graph", "fail", str(exc))
        return report()
    try:
        stock = load_stock(store, config.stock_ref)
        unresolved = [
            mid for mid in nodes if mid not in steps and identities[mid] not in stock.identities
        ]
        if unresolved:
            raise ValueError(f"Non-stock terminal occurrences: {unresolved}")
        add("stock", "pass", "all_terminals_in_snapshot", evidence=(config.stock_ref,))
    except IntegrityError as exc:
        add("stock", "error", str(exc))
    except Exception as exc:
        add("stock", "fail", str(exc))
    for step in route.steps:
        try:
            prediction = Prediction.model_validate(store.prediction(step.prediction_ref))
            manifest = ModelManifest.model_validate(
                store.get(prediction.manifest_ref, "model_manifest")
            )
            if prediction.status != "ok" or prediction.manifest_ref != config.backward_manifest:
                raise ValueError("Wrong model binding or failed source prediction")
            if prediction.requested_count != config.prediction_count:
                raise ValueError("Source prediction count differs from the run configuration")
            source = [c for c in prediction.candidates if c.index == step.candidate_index]
            if len(source) != 1 or not isinstance(source[0], Candidate):
                raise ValueError("Missing successful source candidate")
            candidate = source[0]
            if prediction.effective_input != candidate.product.canonical_smiles:
                raise ValueError("Candidate product is not the effective inference input")
            if candidate.product.canonical_smiles != identities[step.product_id]:
                raise ValueError("Prediction product identity differs from exported product")
            exported = {identities[mid] for mid in step.precursor_ids}
            authoritative = {
                require_molecule(m.original_smiles).canonical_smiles for m in candidate.precursors
            }
            if exported != authoritative:
                raise ValueError("Export changed the authoritative precursor dependencies")
            if len(exported) != len(step.precursor_ids):
                raise ValueError(
                    "Duplicate dependency occurrences; use unique availability dependencies"
                )
            if candidate.cost != score_cost(candidate.score, manifest):
                raise ValueError("Candidate cost transformation mismatch")
            candidates[step.id] = candidate
            templates[step.id] = manifest.templates.get(str(candidate.template_id))
            add(
                f"binding:{step.id}",
                "pass",
                "matches_immutable_adapter_candidate",
                evidence=(step.prediction_ref, prediction.manifest_ref),
                inputs={"candidate_index": step.candidate_index},
            )
            status, reason = mapping_status(candidate.mapped_reaction)
            if candidate.mapped_reaction and status == "pass":
                reactants, product = candidate.mapped_reaction.split(">>")
                if (
                    require_molecule(product).canonical_smiles != candidate.product.canonical_smiles
                    or require_molecule(reactants).canonical_smiles
                    != require_molecule(
                        ".".join(m.canonical_smiles for m in candidate.precursors)
                    ).canonical_smiles
                ):
                    status, reason = "fail", "mapping_reaction_identity_mismatch"
            mapping_mandatory = (
                config.mapping_profile == "mapping-required" or candidate.mapping_required
            )
            add(
                f"mapping:{step.id}",
                status,
                reason,
                mandatory=mapping_mandatory,
                evidence=(step.prediction_ref,),
                settings={"quarantined": status == "fail"},
            )
            coverage["checked" if status in ("pass", "fail") else "missing"] += 1
            if status == "fail":
                coverage["failed"] += 1
            if manifest.kind == "template_based":
                template = manifest.templates.get(str(candidate.template_id))
                if template is None:
                    raise ValueError("Candidate template is absent from bound vocabulary")
                if candidate.mapping_required and status != "pass":
                    add(f"template:{step.id}", "unknown", "required_mapping_unavailable")
                else:
                    try:
                        outcomes = rdchiralRunText(
                            template, prediction.effective_input, **manifest.template_settings
                        )
                        allowed = [
                            {require_molecule(s).canonical_smiles for s in output.split(".")}
                            for output in outcomes
                        ]
                        add(
                            f"template:{step.id}",
                            "pass" if authoritative in allowed else "fail",
                            "template_replay_match"
                            if authoritative in allowed
                            else "template_replay_mismatch",
                            evidence=(prediction.manifest_ref,),
                        )
                    except Exception as exc:
                        add(f"template:{step.id}", "error", f"template_execution_error: {exc}")
            else:
                add(f"template:{step.id}", "not_applicable", "template_free_prediction")
        except IntegrityError as exc:
            add(f"binding:{step.id}", "error", str(exc))
        except Exception as exc:
            add(f"binding:{step.id}", "fail", str(exc))
    if len(candidates) == len(route.steps):
        import math

        total_cost = math.fsum(candidate.cost for candidate in candidates.values())
        if not math.isclose(route.search_cost, total_cost, rel_tol=1e-12, abs_tol=1e-12):
            add("search_cost", "fail", "exported_search_cost_differs_from_selected_candidates")
        else:
            add("search_cost", "pass", "search_cost_reconstructed")
    rejected = disposition(checks) == "rejected"
    for step in route.steps:
        if (rejected and not config.full_diagnostics) or step.id not in candidates:
            add(
                f"forward:{step.id}",
                "not_checked",
                "structural_failure_or_missing_binding",
                mandatory=False,
            )
            precedent[step.id] = {"status": "not_checked"}
        else:
            result = forward_check(forward, candidates[step.id], config.forward_k)
            checks.append(result.model_copy(update={"name": f"forward:{step.id}"}))
            precedent[step.id] = precedent_lookup(
                store, config.corpus_ref, candidates[step.id], templates.get(step.id)
            )
    return report()
