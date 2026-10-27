from __future__ import annotations

import csv
import hashlib
import io
from typing import Any

from chemlab.chemistry import require_molecule
from chemlab.records import Corpus, PrecedentSource
from chemlab.registry import Registry
from chemlab.store import Store


def public_training_csv(raw: bytes, metadata: dict[str, Any]) -> tuple[Corpus, dict[str, Any]]:
    expected = metadata["sha"]
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if actual != expected:
        raise ValueError("Public dataset bytes differ from the recorded Git blob")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if not {"id", "rxn_smiles"}.issubset(reader.fieldnames or []):
        raise ValueError("Reaction CSV requires id and rxn_smiles columns")
    records, quarantined = [], []
    total = 0
    for number, row in enumerate(reader, start=1):
        total += 1
        try:
            left, _agents, product = row["rxn_smiles"].split(">")
            if not row["id"] or not left or not product:
                raise ValueError("Missing source ID or represented reaction participant")
            require_molecule(product)
            precursors = tuple(left.split("."))
            for precursor in precursors:
                require_molecule(precursor)
            # Preserve mapped source strings; identity is recomputed by retrieval.
            records.append(
                PrecedentSource(
                    source_id=f"{row['id']}:train-row-{number}",
                    product=product,
                    precursors=precursors,
                    reference=f"https://patents.google.com/patent/{row['id']}",
                )
            )
        except Exception as exc:
            quarantined.append({"row": number, "original": row, "error": str(exc)})
    sha256 = hashlib.sha256(raw).hexdigest()
    corpus = Corpus(
        name="USPTO-50K OpenRetro training / supported records",
        version=f"gitblob:{actual};sha256:{sha256}",
        partition="training",
        source=metadata["html_url"] + "; training split only; model/PaRoutes overlap not audited",
        license="OpenRetro repository MIT; underlying dataset license not separately specified",
        multiplicity="occurrences",
        records=tuple(records),
    )
    audit = {
        "input_records": total,
        "accepted_records": len(records),
        "quarantined": quarantined,
        "source_sha256": sha256,
        "git_blob": actual,
        "partition": "training",
        "policy": (
            "original mapped participants; split disconnected source fragments; "
            "preserve occurrences"
        ),
        "limitations": (
            "Reported represented reactions; no independent confirmation or full procedure claim"
        ),
    }
    return corpus, audit


def register_public_training(store: Store, raw: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
    corpus, audit = public_training_csv(raw, metadata)
    audit_ref = store.put("corpus_ingestion_report", audit)
    source_ref = store.put("source_csv", {"metadata": metadata, "text": raw.decode("utf-8")})
    corpus = corpus.model_copy(
        update={"source_artifact_ref": source_ref, "ingestion_report_ref": audit_ref}
    )
    corpus_ref = store.put("corpus", corpus)
    Registry(store).register("uspto50k-training-v1", "corpus", corpus_ref)
    return {
        "corpus_ref": corpus_ref,
        "audit_ref": audit_ref,
        "source_ref": source_ref,
        "input_records": audit["input_records"],
        "accepted_records": audit["accepted_records"],
        "quarantined_count": len(audit["quarantined"]),
        "version": corpus.version,
        "license": corpus.license,
        "limitations": corpus.source,
    }
