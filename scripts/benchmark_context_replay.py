"""Measure within-process duplicate extraction replay, with full result parity."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from chemlab.evaluation import context_replay as experiment
from chemlab.evidence import reaction_templates as templates
from chemlab.evidence.reaction_library import ReactionLibrary, parse_patent_line
from chemlab.records import canonical_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest_hash")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Benchmark runs are immutable")
    protocol = {
        "regime": "Within-process duplicate replay; not first-execution inference",
        "source_rows": 128,
        "repetitions": 8,
        "canary_repetitions": 64,
        "warmup_blocks": 2,
        "drift_limit": 0.10,
        "order": "Alternate AB and BA by repetition; fastest sample per variant",
        "scope": "Context extraction only; no finished-dispatch or cold-start claim",
    }
    args.output.mkdir(parents=True)
    (args.output / "protocol.json").write_bytes(canonical_bytes(protocol))
    source = ReactionLibrary(args.source, args.manifest_hash)
    with sqlite3.connect(source.database.as_uri() + "?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT source,row_number,raw FROM records WHERE error IS NULL "
            "ORDER BY source,row_number LIMIT 128"
        ).fetchall()
    inputs = []
    for _, _, raw in rows:
        record = parse_patent_line(raw)
        inputs.append((record["mapped_reaction"], record["product"], tuple(record["precursors"])))
    experiment.observed_context.cache_clear()
    baseline = [templates._extract_context(*query) for query in inputs]
    assert [experiment.replay_context(*query) for query in inputs] == baseline
    canary_input = next(
        query
        for query, result in zip(inputs, baseline, strict=True)
        if result["status"] == "observed"
    )

    def timed(function, queries):
        start = time.perf_counter()
        results = [function(*query) for query in queries]
        return time.perf_counter() - start, results

    for _ in range(protocol["warmup_blocks"]):
        timed(templates._extract_context, inputs)
        timed(experiment.replay_context, inputs)
    measurements = []
    for rep in range(protocol["repetitions"]):
        before, _ = timed(
            templates._extract_context, [canary_input] * protocol["canary_repetitions"]
        )
        variants = [("baseline", templates._extract_context), ("cached", experiment.replay_context)]
        if rep % 2:
            variants.reverse()
        sample = {}
        for name, function in variants:
            elapsed, outputs = timed(function, inputs)
            assert outputs == baseline
            sample[name] = elapsed
        after, _ = timed(
            templates._extract_context, [canary_input] * protocol["canary_repetitions"]
        )
        measurements.append({"rep": rep, **sample, "canary_before": before, "canary_after": after})
    canaries = [r[key] for r in measurements for key in ("canary_before", "canary_after")]
    drift = max(canaries) / min(canaries) - 1
    valid = drift <= protocol["drift_limit"]
    best_baseline = min(r["baseline"] for r in measurements)
    best_cached = min(r["cached"] for r in measurements)
    report = {
        "protocol": protocol,
        "source_library_ref": source.manifest_ref,
        "input_rows": [{"source": source, "row": number} for source, number, _ in rows],
        "full_output_parity": True,
        "measurements": measurements,
        "canary_drift": drift,
        "measurement_valid": valid,
        "fastest_baseline_seconds": best_baseline,
        "fastest_cached_seconds": best_cached,
        "ratio": best_baseline / best_cached if valid else None,
        "decision": "measured_replay_win"
        if valid and best_cached < best_baseline
        else "unusable_or_no_win",
    }
    (args.output / "report.json").write_bytes(canonical_bytes(report))
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "full_output_parity",
                    "canary_drift",
                    "measurement_valid",
                    "ratio",
                    "decision",
                )
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
