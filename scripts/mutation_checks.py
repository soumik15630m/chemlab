"""Seed isolated behavioral defects; require assertion failures, not setup errors."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

MUTATIONS = [
    (
        "M57-mapper-venv-interpreter-boundary",
        "scripts/setup_reaction_knowledge.py",
        "str(interpreter.absolute())",
        "str(interpreter.resolve())",
        "tests/test_bootstrap.py::test_mapper_interpreter_symlink_keeps_the_selected_virtual_environment",
    ),
    (
        "M56-library-identity-policy-admission",
        "chemlab/evidence/reaction_library.py",
        'if self.manifest.get("identity") != "identity-v1":',
        "if False:",
        "tests/test_reaction_library.py::test_loader_checks_declared_identity_and_evidence_partition_independently",
    ),
    (
        "M55-replay-command-failure-exit",
        "chemlab/cli.py",
        'or result.get("equivalent") is False',
        "or False",
        "tests/test_reaction_templates.py::test_cli_context_evidence_replays_saved_maps_and_returns_nonzero_for_changed_findings",
    ),
    (
        "M54-reaction-batch-hash-aliasing",
        "chemlab/evidence/reaction_library.py",
        "if key in indexed and indexed[key] != query:",
        "if False:",
        "tests/test_reaction_library.py::test_batch_index_keeps_full_identities_and_refuses_hash_aliasing",
    ),
    (
        "M53-template-enumeration-order",
        "chemlab/evidence/reaction_templates.py",
        "normalized.sort(key=canonical_bytes)",
        "normalized.sort(key=canonical_bytes, reverse=True)",
        "tests/test_reaction_templates.py::test_replay_enumeration_has_stable_order_and_preserves_duplicate_outputs",
    ),
    (
        "M52-required-route-step-outcomes",
        "chemlab/evidence/chemical_service.py",
        'if counts["contradiction"]:',
        "if False:",
        "tests/test_chemical_service.py::test_route_evidence_never_averages_away_a_failed_or_unresolved_required_step",
    ),
    (
        "M51-unstable-engine-input-admission",
        "chemlab/chemistry/identity.py",
        "if require_molecule(result.canonical_smiles).canonical_smiles != result.canonical_smiles:",
        "if False:",
        "tests/test_identity.py::test_known_stereo_cycle_is_preserved_as_observation_but_cannot_enter_engine",
    ),
    (
        "M50-unhashed-index-state",
        "chemlab/evidence/reaction_library.py",
        "if any(path.with_name(path.name + suffix).exists() "
        'for suffix in ("-wal", "-shm", "-journal")):',
        "if False:",
        "tests/test_reaction_library.py::test_unhashed_sqlite_sidecars_cannot_supply_immutable_evidence",
    ),
    (
        "M49-dependency-deadline-enforcement",
        "chemlab/evidence/bounded.py",
        "timeout=timeout).result()",
        "timeout=None).result()",
        "tests/test_bounded_dependencies.py::test_dependency_deadline_interrupts_worker_and_next_operation_recovers",
    ),
    (
        "M48-active-chemical-snapshot-gate",
        "chemlab/distribution.py",
        "def ensure_no_active_chemical_jobs(conn: sqlite3.Connection) -> None:",
        "def ensure_no_active_chemical_jobs(conn: sqlite3.Connection) -> None:\n    return",
        "tests/test_distribution.py::test_active_chemical_job_cannot_be_published_as_runtime_snapshot",
    ),
    (
        "M46-index-copy-publication",
        "chemlab/evidence/reaction_library.py",
        "if copied.hexdigest() != expected or file_digest(destination / database) != expected:",
        "if False:",
        "tests/test_reaction_library.py::test_corrupt_copy_source_cannot_publish_a_completion_marker",
    ),
    (
        "M47-chemical-job-policy-binding",
        "chemlab/evidence/chemical_service.py",
        'if request["policy_hash"] != digest(POLICY):',
        "if False:",
        "tests/test_chemical_service.py::test_policy_change_after_submission_cannot_publish_a_completed_job",
    ),
    (
        "M45-hydrogen-isotope-provenance",
        "chemlab/evidence/reaction_diagnostics.py",
        "if a.GetAtomicNum() > 1 or a.GetIsotope()",
        "if a.GetAtomicNum() > 1",
        "tests/test_chemical_checks.py::test_listed_atom_obligation_has_positive_negative_and_unknown_controls",
    ),
    (
        "M44-chemical-export-precursor-multiplicity",
        "chemlab/reporting/chemical_exports.py",
        'for smiles in query["precursors"]:',
        'for smiles in set(query["precursors"]):',
        "tests/test_chemical_service.py::test_evidence_pdf_and_editable_files_keep_bindings_and_uncertainty",
    ),
    (
        "M34-patent-source-integrity",
        "chemlab/evidence/reaction_library.py",
        "if file_digest(path) != expected:",
        "if False:",
        "tests/test_reaction_library.py::test_unsupported_and_broken_sources_remain_quarantined",
    ),
    (
        "M35-reaction-occurrence-identity",
        "chemlab/evidence/reaction_library.py",
        '"precursors": sorted(stable_identity(s) for s in precursors),',
        '"precursors": sorted({stable_identity(s) for s in precursors}),',
        "tests/test_reaction_library.py::test_lookup_exact_identity_occurrences_and_duplicate_provenance",
    ),
    (
        "M36-exact-template-replay",
        "chemlab/evidence/reaction_templates.py",
        'exact = query["precursors"] in normalized',
        "exact = bool(normalized)",
        "tests/test_reaction_templates.py::test_public_extractor_and_replay_are_bound_to_precursor_identity",
    ),
    (
        "M37-mapping-proposal-binding",
        "chemlab/evidence/chemical_checks.py",
        'if proposal["input_key"] != digest(query) or proposal["input"] != query:',
        "if False:",
        "tests/test_chemical_checks.py::test_misbound_element_incompatible_partial_and_error_maps_cannot_supply_edits",
    ),
    (
        "M38-atom-origin-obligation",
        "chemlab/evidence/chemical_checks.py",
        'checks["listed_atom_sources"] = {',
        'contradiction = False\n    checks["listed_atom_sources"] = {',
        "tests/test_chemical_checks.py::test_listed_atom_obligation_has_positive_negative_and_unknown_controls",
    ),
    (
        "M39-human-reference-conflicts",
        "chemlab/evaluation/chemical_reference.py",
        "if len(labels) != 1:",
        "if False:",
        "tests/test_chemical_reference.py::test_duplicate_conflicts_and_denominators_are_not_silent_truth",
    ),
    (
        "M40-batch-end-integrity",
        "chemlab/evidence/reaction_library.py",
        "if file_digest(self.database) != expected:\n"
        '                raise IntegrityError("Reaction library changed during evidence batch")',
        "if False:\n"
        '                raise IntegrityError("Reaction library changed during evidence batch")',
        "tests/test_reaction_templates.py::test_batch_does_not_return_a_publishable_success_after_source_changes",
    ),
    (
        "M41-reference-source-checksum",
        "chemlab/evaluation/chemical_reference.py",
        'if len(raw) != protocol["bytes"] or blob != protocol["git_blob"]:',
        'if len(raw) != protocol["bytes"]:',
        "tests/test_chemical_reference.py::test_reference_source_and_result_bindings_are_checked",
    ),
    (
        "M42-final-source-template-firewall",
        "chemlab/evidence/reaction_templates.py",
        'if record["key"] in excluded:',
        "if False:",
        "tests/test_reaction_templates.py::test_source_context_support_keeps_scope_and_excludes_final_sources",
    ),
    (
        "M43-chemical-export-binding",
        "chemlab/reporting/chemical_exports.py",
        'if digest(query) != key or reaction["input_key"] != key:',
        "if False:",
        "tests/test_chemical_service.py::test_evidence_pdf_and_editable_files_keep_bindings_and_uncertainty",
    ),
    (
        "M33-stock-identity-stability",
        "chemlab/evidence/stock_sources.py",
        "if require_molecule(identity).canonical_smiles != identity:",
        "if False:",
        "tests/test_stock_sources.py::test_actual_ursa_stereo_identity_cycle_is_quarantined_without_rewriting",
    ),
    (
        "M32-stock-download-integrity",
        "chemlab/evidence/stock_sources.py",
        "if hashlib.sha256(data).hexdigest() != sha256 or "
        "(size is not None and len(data) != size):",
        "if size is not None and len(data) != size:",
        "tests/test_stock_sources.py::test_failed_download_does_not_publish_a_completed_source",
    ),
    (
        "M26-stock-source-checksum",
        "chemlab/evidence/stock_sources.py",
        "if len(raw) != spec.size or hashlib.sha256(raw).hexdigest() != spec.sha256:",
        "if len(raw) != spec.size:",
        "tests/test_stock_sources.py::test_pinned_source_mismatch_row_count_and_card_are_rejected",
    ),
    (
        "M27-stock-union-completeness",
        "chemlab/evidence/checks.py",
        "if set(stock.identities) != expected:",
        "if not set(stock.identities).issubset(expected):",
        "tests/test_stock_sources.py::test_union_is_exact_order_independent_and_retains_component_terms",
    ),
    (
        "M28-stock-fragment-preservation",
        "chemlab/evidence/stock_sources.py",
        "identity = require_molecule(row[spec.smiles_column]).canonical_smiles",
        'identity = require_molecule(row[spec.smiles_column].split(".")[0]).canonical_smiles',
        "tests/test_stock_sources.py::test_csv_import_keeps_full_identity_and_duplicate_source_records",
    ),
    (
        "M29-legacy-stock-encoding",
        "chemlab/records.py",
        "if data.get(key) in (None, [], ()):",
        "if False:",
        "tests/test_stock_sources.py::test_legacy_stock_encoding_and_alias_are_unchanged",
    ),
    (
        "M30-stock-source-bundle-closure",
        "chemlab/reporting/bundles.py",
        'elif kind == "stock":',
        'elif kind == "unsupported_stock":',
        "tests/test_stock_sources.py::test_stock_sources_and_union_components_are_in_complete_bundles",
    ),
    (
        "M31-stock-source-id-uniqueness",
        "chemlab/evidence/stock_sources.py",
        "if not source_id.strip() or source_id in seen_ids:",
        "if not source_id.strip():",
        "tests/test_stock_sources.py::test_malformed_or_key_only_stocks_are_not_admitted",
    ),
    (
        "M25-precedent-product-specificity",
        "chemlab/evidence/checks.py",
        "require_molecule(record.product).canonical_smiles\n"
        "                == candidate.product.canonical_smiles",
        "True",
        "tests/test_evidence.py::test_precedent_cannot_transfer_from_a_carbonyl_analog_to_the_requested_product",
    ),
    (
        "M24-observation-prediction-integrity",
        "chemlab/evidence/reaction_diagnostics.py",
        'envelope is None or digest(envelope) != ref or envelope.get("kind") != kind',
        'envelope is None or envelope.get("kind") != kind',
        "tests/test_reaction_diagnostics.py::test_diagnostics_require_original_prediction_hash_even_when_chemistry_is_unchanged",
    ),
    (
        "M20-diagnostic-occurrence-counts",
        "chemlab/evidence/reaction_diagnostics.py",
        "for smiles in precursors:",
        "for smiles in set(precursors):",
        "tests/test_reaction_diagnostics.py::test_atom_inventory_keeps_occurrences_isotopes_and_omitted_reagent_limits",
    ),
    (
        "M21-mapping-input-binding",
        "chemlab/evidence/reaction_diagnostics.py",
        "if (\n            require_molecule(left).canonical_smiles",
        "if False and (\n            require_molecule(left).canonical_smiles",
        "tests/test_reaction_diagnostics.py::test_invalid_or_inapplicable_mapping_never_supplies_edits",
    ),
    (
        "M22-tautomer-enumeration-completeness",
        "chemlab/evidence/reaction_diagnostics.py",
        'if str(result.status) != "Completed":',
        "if False:",
        "tests/test_reaction_diagnostics.py::test_tautomer_diagnostic_preserves_rank_identity_and_complete_enumeration",
    ),
    (
        "M23-chemical-overclaim",
        "chemlab/evidence/reaction_diagnostics.py",
        '"chemical_assessment": "unresolved" if steps else "not_applicable",',
        '"chemical_assessment": "established" if steps else "not_applicable",',
        "tests/test_reaction_diagnostics.py::test_observations_endpoint_is_bound_read_only_and_preserves_positive_route",
    ),
    (
        "M17-mol-stereochemistry",
        "chemlab/reporting/formats.py",
        "block = Chem.MolToV3KMolBlock(mol)",
        "Chem.RemoveStereochemistry(mol)\n    block = Chem.MolToV3KMolBlock(mol)",
        "tests/test_exports.py::test_mol_roundtrip_preserves_declared_identity",
    ),
    (
        "M18-reaction-export-direction",
        "chemlab/reporting/formats.py",
        "reaction.AddProductTemplate(depiction_molecule(molecules[step.product_id]))",
        "reaction.AddReactantTemplate(depiction_molecule(molecules[step.product_id]))",
        "tests/test_exports.py::test_reaction_export_keeps_forward_direction_multiplicity_and_fragments",
    ),
    (
        "M19-pdf-fixture-disclosure",
        "chemlab/reporting/pdf.py",
        'if run.get("experimental"):',
        "if False:",
        "tests/test_exports.py::test_pdf_keeps_evidence_scope_and_fixture_warning",
    ),
    (
        "M15-snapshot-byte-preservation",
        "chemlab/distribution.py",
        "shutil.copyfileobj(input_file, output)",
        "output.write(b'')",
        "tests/test_distribution.py::test_snapshot_restores_registry_objects_and_complete_bundles",
    ),
    (
        "M16-lfs-materialization-gate",
        "scripts/fetch_pretrained.py",
        'if stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1\\n"):',
        "if False:",
        "tests/test_distribution.py::test_lfs_pointer_is_not_a_model_checkpoint",
    ),
    (
        "M14-compose-initialization-gate",
        "compose.yaml",
        "service_completed_successfully",
        "service_started",
        "tests/test_bootstrap.py::test_compose_initialization_gate_and_persistent_mounts",
    ),
    (
        "M13-bootstrap-failure-propagation",
        "chemlab/bootstrap.py",
        "cwd=root,\n        env=env,\n        check=True,",
        "cwd=root,\n        env=env,\n        check=False,",
        "tests/test_bootstrap.py::test_download_failure_blocks_registration",
    ),
    (
        "M11-venv-isolation",
        "chemlab/bootstrap.py",
        "python = virtual_python(directory, sys.platform)",
        "python = Path(sys.executable)",
        "tests/test_bootstrap.py::test_native_installs_and_runs_only_selected_virtual_interpreter",
    ),
    (
        "M12-setup-only-no-server",
        "chemlab/bootstrap.py",
        "if args.prepare_only:\n        return 0",
        "if False:\n        return 0",
        "tests/test_bootstrap.py::test_prepare_only_has_no_server_side_effect",
    ),
    (
        "M10-public-source-integrity",
        "chemlab/evidence/ingestion.py",
        "if actual != expected:",
        "if False:",
        "tests/test_ingestion.py::test_source_blob_mismatch_is_rejected",
    ),
    (
        "M09-tokenizer-admission",
        "chemlab/adapters/sdk.py",
        "if any(token not in tokenizer.vocab_dict for token in tokens):",
        "if False:",
        "tests/test_plugins.py::test_tokenizer_cannot_silently_lose_input_information",
    ),
    (
        "M01-stereo-preservation",
        "chemlab/chemistry/identity.py",
        "isomericSmiles=True",
        "isomericSmiles=False",
        "tests/test_identity.py::test_identity_contract",
    ),
    (
        "M02-ancestor-recurrence",
        "chemlab/verification/verifier.py",
        "mid in reached or identities[mid] in ancestors",
        "mid in reached",
        "tests/test_verification.py::test_molecular_cycle_with_fresh_occurrences",
    ),
    (
        "M03-precursor-completeness",
        "chemlab/verification/verifier.py",
        "if exported != authoritative:",
        "if False:",
        "tests/test_verification.py::test_export_corruptions_are_rejected[drop_precursor]",
    ),
    (
        "M04-score-direction",
        "chemlab/adapters/models.py",
        "(candidate.cost, candidate.index) < (",
        "(candidate.cost, candidate.index) > (",
        "tests/test_adapters.py::test_lower_cost_duplicate_wins",
    ),
    (
        "M05-fail-precedence",
        "chemlab/verification/verifier.py",
        'if any(c.status == "fail" for c in mandatory):',
        "if False:",
        "tests/test_verification.py::test_fail_dominates_unknown",
    ),
    (
        "M06-cache-integrity",
        "chemlab/store.py",
        "if hashlib.sha256(data).hexdigest() != ref:",
        "if False:",
        "tests/test_infrastructure.py::test_corrupt_artifact_is_never_a_cache_hit",
    ),
    (
        "M07-expansion-accounting",
        "chemlab/adapters/models.py",
        "self.logical_expansions += len(inputs)",
        "self.logical_expansions += 0",
        "tests/test_adapters.py::test_cache_preserves_logical_attempts",
    ),
    (
        "M08-report-binding",
        "chemlab/reporting/bundles.py",
        "if report.route_hash != digest(route):",
        "if False:",
        "tests/test_infrastructure.py::test_report_for_another_route_cannot_publish",
    ),
]


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    baseline = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--basetemp=/tmp/mutation-baseline",
            "-o",
            "cache_dir=/tmp/mutation-cache",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if baseline.returncode:
        raise RuntimeError("Mutation baseline failed:\n" + baseline.stdout + baseline.stderr)
    results = []
    for name, filename, old, new, test in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="chemlab-mutant-") as temp:
            directory = Path(temp)
            shutil.copyfile(root / "compose.yaml", directory / "compose.yaml")
            shutil.copytree(
                root / "scripts",
                directory / "scripts",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            shutil.copytree(
                root / "chemlab",
                directory / "chemlab",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            shutil.copytree(
                root / "tests", directory / "tests", ignore=shutil.ignore_patterns("__pycache__")
            )
            path = directory / filename
            original = path.read_text(encoding="utf-8")
            if old not in original:
                raise RuntimeError(f"Mutation anchor missing: {name}")
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": str(directory), "PYTHONDONTWRITEBYTECODE": "1"}
            output = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    test,
                    "-q",
                    "--basetemp",
                    str(directory / "tmp"),
                    "--junitxml",
                    str(directory / "result.xml"),
                    "-o",
                    "cache_dir=/tmp/mutation-cache",
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            suite = ET.parse(directory / "result.xml").getroot()
            failures = sum(int(s.get("failures", 0)) for s in suite.iter("testsuite"))
            errors = sum(int(s.get("errors", 0)) for s in suite.iter("testsuite"))
            detected = output.returncode == 1 and failures > 0 and errors == 0
            results.append(
                {
                    "name": name,
                    "test": test,
                    "detected": detected,
                    "assertion_failures": failures,
                    "setup_errors": errors,
                }
            )
            print(f"{name}: {'detected' if detected else 'SURVIVED OR INVALID'}", flush=True)
    return {
        "baseline_passed": True,
        "mutants": results,
        "passed": all(r["detected"] for r in results),
        "scope": f"{len(MUTATIONS)} named behavioral mutants; no exhaustive coverage claim",
    }


if __name__ == "__main__":
    report = run()
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/mutation-report.json")
    destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    raise SystemExit(0 if report["passed"] else 1)
