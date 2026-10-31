from __future__ import annotations

from collections import Counter
from typing import Any

from chemlab.adapters.models import ModelService
from chemlab.chemistry import require_molecule, require_stable_molecule
from chemlab.chemistry.identity import stereo_relation
from chemlab.records import Candidate, Check, Corpus, Molecule, Status, Stock, canonical_bytes
from chemlab.store import Store


def import_stock(store: Store, smiles: list[str], name: str, source: str, license: str) -> str:
    identities = tuple(sorted({require_stable_molecule(s).canonical_smiles for s in smiles}))
    return store.put(
        "stock", Stock(name=name, source=source, license=license, identities=identities)
    )


def load_stock(store: Store, ref: str, _ancestors: frozenset[str] = frozenset()) -> Stock:
    if ref in _ancestors:
        raise ValueError("Stock provenance has a component cycle")
    stock = Stock.model_validate(store.get(ref, "stock"))
    for identity in stock.identities:
        if require_molecule(identity).canonical_smiles != identity:
            raise ValueError("Stock contains a noncanonical identity")
    if len(set(stock.identities)) != len(stock.identities):
        raise ValueError("Stock contains duplicate identities")
    if bool(stock.source_artifact_ref) != bool(stock.ingestion_report_ref):
        raise ValueError("Imported stock requires both source and ingestion report")
    if stock.source_artifact_ref:
        if stock.component_refs:
            raise ValueError("A stock cannot be both a CSV import and a component union")
        from chemlab.evidence.stock_sources import validate_imported_stock

        validate_imported_stock(store, stock)
    if stock.component_refs:
        if tuple(sorted(set(stock.component_refs))) != stock.component_refs:
            raise ValueError("Stock components must be unique and sorted")
        expected: set[str] = set()
        license_terms = []
        for parent in stock.component_refs:
            component = load_stock(store, parent, _ancestors | {ref})
            expected.update(component.identities)
            license_terms.append({"stock_ref": parent, "license": component.license})
        if set(stock.identities) != expected:
            raise ValueError("Stock identities differ from the exact component union")
        if stock.license != (
            "Component terms apply separately: " + canonical_bytes(license_terms).decode("ascii")
        ):
            raise ValueError("Stock union terms differ from component license records")
    return stock


def forward_check(service: ModelService | None, candidate: Candidate, k: int) -> Check:
    inputs: dict[str, Any] = {
        "product": candidate.product.canonical_smiles,
        "precursors": [m.canonical_smiles for m in candidate.precursors],
        "k": k,
    }
    if service is None:
        return Check(
            name="forward",
            status="not_checked",
            reason="forward_model_not_configured",
            mandatory=False,
            inputs=inputs,
        )
    try:
        ref, result = service.forward(tuple(inputs["precursors"]), k)
        status: Status = "fail"
        reason = "no_matching_product"
        rank: int | None = None
        if result.status == "error":
            status, reason = "error", "predictor_error"
        elif any(not isinstance(m, Molecule) for m in result.products):
            status, reason = "error", "uninterpretable_output"
        elif result.information_lost:
            status, reason = "unknown", "input_information_loss"
        else:
            relations = [
                stereo_relation(candidate.product.canonical_smiles, m.canonical_smiles)
                for m in result.products
                if isinstance(m, Molecule)
            ]
            if "exact" in relations:
                status, reason, rank = "pass", "exact_identity_match", relations.index("exact") + 1
            elif "compatible_missing_stereo" in relations or "indeterminate" in relations:
                status, reason = "unknown", "stereo_ambiguity"
        return Check(
            name="forward",
            status=status,
            reason=reason,
            mandatory=False,
            inputs=inputs,
            evidence=(ref,),
            settings={
                "matching_rank": rank,
                "k": k,
                "manifest_ref": service.manifest_ref,
                "conditions": "not_checked",
            },
        )
    except Exception as exc:
        return Check(
            name="forward",
            status="error",
            reason="forward_execution_error",
            mandatory=False,
            inputs=inputs,
            settings={"error": str(exc)},
        )


def precedent_lookup(
    store: Store, corpus_ref: str | None, candidate: Candidate, template_smarts: str | None = None
) -> dict[str, Any]:
    if corpus_ref is None:
        return {"status": "not_checked", "reason": "corpus_not_configured"}
    try:
        corpus = Corpus.model_validate(store.get(corpus_ref, "corpus"))
        if corpus.partition == "final_reference":
            raise ValueError("Final-reference records cannot supply inference evidence")
        if corpus.source_artifact_ref:
            store.get(corpus.source_artifact_ref, "source_csv")
        if corpus.ingestion_report_ref:
            store.get(corpus.ingestion_report_ref, "corpus_ingestion_report")

        def key(precursors):
            ids = [require_molecule(s).canonical_smiles for s in precursors]
            return (
                sorted(Counter(ids).items())
                if corpus.multiplicity == "occurrences"
                else sorted(set(ids))
            )

        query = key([p.canonical_smiles for p in candidate.precursors])
        exact, templates = [], []
        references = {}
        for record in corpus.records:
            if (
                require_molecule(record.product).canonical_smiles
                == candidate.product.canonical_smiles
                and key(record.precursors) == query
            ):
                exact.append(record.source_id)
                references[record.source_id] = record.reference
            elif template_smarts is not None and record.template_smarts == template_smarts:
                templates.append(record.source_id)
                references[record.source_id] = record.reference
        return {
            "status": "pass",
            "corpus_ref": corpus_ref,
            "corpus": corpus.name,
            "version": corpus.version,
            "partition": corpus.partition,
            "multiplicity_policy": corpus.multiplicity,
            "match_type": "exact_represented_reaction"
            if exact
            else "template_only"
            if templates
            else "none",
            "exact_source_ids": sorted(exact),
            "template_source_ids": sorted(templates),
            "references": references,
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "corpus_ref": corpus_ref}
