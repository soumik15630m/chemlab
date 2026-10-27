from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from chemlab.adapters.sdk import content_hash
from chemlab.application import Application
from chemlab.evaluation.datasets import audit, export_training, read_examples
from chemlab.evidence.checks import import_stock
from chemlab.records import Corpus, ModelManifest, RunConfig, canonical_bytes
from chemlab.registry import Registry, load_manifest, parity
from chemlab.reporting.bundles import read_bundle
from chemlab.store import Store
from chemlab.verification import verify


def setup_pretrained(store: Store, root: Path) -> dict:
    registry = Registry(store)
    refs = {}
    for alias, cls in [
        ("generator", "RetroChimeraDeNovoModel"),
        ("checker", "ForwardChimeraDeNovoModel"),
    ]:
        checkpoint = (root / alias).resolve()
        tokenizer = checkpoint / "vocab.txt"
        source = json.loads((root / f"{alias}-source.json").read_text(encoding="utf-8"))
        model_kind: Literal["template_free", "forward"] = (
            "forward" if alias == "checker" else "template_free"
        )
        manifest = ModelManifest(
            name=source["title"],
            kind=model_kind,
            backend="syntheseus",
            checkpoint=str(checkpoint),
            checkpoint_hash=content_hash(checkpoint),
            training_provenance=("Pistachio; overlap with evaluation not yet audited"),
            license=source["license"]["name"],
            score_semantics="probability",
            score_direction="higher",
            model_class=f"retrochimera:{cls}",
            architecture_id="R-SMILES-2",
            representation="smiles",
            tokenizer_path=str(tokenizer),
            tokenizer_hash=content_hash(tokenizer),
            determinism="seeded",
            inference_seed=0,
            device="cpu",
            dtype="float32",
            decoding={
                "beam_size": 10,
                "augmentation_size": 1,
                "max_generated_seq_len": 512,
                "probability_from_score_temperature": 3.0,
                "filter_duplicate_augmentations": True,
            },
        )
        refs[alias] = registry.register_model(f"{alias}-v1", manifest)
    stock_path = root / "paroutes-n1-stock.txt"
    refs["stock"] = import_stock(
        store,
        stock_path.read_text(encoding="utf-8").splitlines(),
        "PaRoutes v2 n1",
        "https://zenodo.org/records/7341155",
        "CC-BY-4.0",
    )
    registry.register("paroutes-n1-v2", "stock", refs["stock"])
    from chemlab.evidence.ingestion import register_public_training

    metadata = json.loads((root / "openretro-train-source.json").read_text(encoding="utf-8"))
    corpus = register_public_training(store, (root / "openretro-train.csv").read_bytes(), metadata)
    refs["corpus"] = corpus["corpus_ref"]
    return refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chemlab")
    parser.add_argument("--store", type=Path, default=Path("var"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    register = commands.add_parser("register-model")
    register.add_argument("alias")
    register.add_argument("manifest", type=Path)
    stock = commands.add_parser("import-stock")
    stock.add_argument("alias")
    stock.add_argument("file", type=Path)
    stock.add_argument("--source", required=True)
    stock.add_argument("--license", required=True)
    corpus = commands.add_parser("import-corpus")
    corpus.add_argument("alias")
    corpus.add_argument("file", type=Path)
    setup = commands.add_parser("setup-pretrained")
    setup.add_argument("--models", type=Path, default=Path("models"))
    run = commands.add_parser("run")
    run.add_argument("target")
    run.add_argument("--config", type=Path, required=True)
    report = commands.add_parser("show")
    report.add_argument("run_id")
    check = commands.add_parser("check-bundle")
    check.add_argument("path", type=Path)
    replay = commands.add_parser("reverify")
    replay.add_argument("run_id")
    parity_cmd = commands.add_parser("parity")
    parity_cmd.add_argument("model")
    parity_cmd.add_argument("inputs", nargs="+")
    parity_cmd.add_argument("--count", type=int, required=True)
    dataset = commands.add_parser("dataset-audit")
    dataset.add_argument("file", type=Path)
    export = commands.add_parser("dataset-export")
    export.add_argument("file", type=Path)
    export.add_argument("output", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    args = parser.parse_args(argv)
    store = Store(args.store)
    registry = Registry(store)
    app = Application(store)
    result: Any = None
    if args.command == "list":
        result = registry.list()
    elif args.command == "register-model":
        result = {"ref": registry.register_model(args.alias, load_manifest(args.manifest))}
    elif args.command == "import-stock":
        ref = import_stock(
            store,
            args.file.read_text(encoding="utf-8").splitlines(),
            args.alias,
            args.source,
            args.license,
        )
        registry.register(args.alias, "stock", ref)
        result = {"ref": ref}
    elif args.command == "import-corpus":
        record = Corpus.model_validate_json(args.file.read_text(encoding="utf-8"))
        ids = [r.source_id for r in record.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Corpus contains duplicate source IDs")
        ref = store.put("corpus", record)
        registry.register(args.alias, "corpus", ref)
        result = {"ref": ref}
    elif args.command == "setup-pretrained":
        result = setup_pretrained(store, args.models)
    elif args.command == "run":
        data = json.loads(args.config.read_text(encoding="utf-8"))
        for field, kind in [
            ("backward_manifest", "model_manifest"),
            ("forward_manifest", "model_manifest"),
            ("stock_ref", "stock"),
            ("corpus_ref", "corpus"),
        ]:
            if data.get(field):
                data[field] = registry.resolve(data[field], kind)
        run_id = app.prepare(args.target, RunConfig.model_validate(data))
        app.execute(run_id)
        result = app.run(run_id)
    elif args.command == "show":
        result = app.run(args.run_id)
    elif args.command == "check-bundle":
        bundle = read_bundle(args.path)
        result = {
            "state": bundle["state"],
            "run_id": bundle["run_id"],
            "files": len(bundle["files"]),
        }
    elif args.command == "parity":
        result = parity(
            store, registry.resolve(args.model, "model_manifest"), args.inputs, args.count
        )
    elif args.command == "reverify":
        row = app.run(args.run_id)
        bundle = row["result"]
        config = RunConfig.model_validate(store.get(row["config_ref"], "run_config"))
        reports = []
        forward = app.model(config.forward_manifest) if config.forward_manifest else None
        for items in bundle["groups"].values():
            for item in items:
                route = bundle["objects"][item["route_ref"]]["payload"]
                old = bundle["objects"][item["report_ref"]]["payload"]
                new = verify(store, route, row["target"], config, forward)
                reports.append(
                    {
                        "route_ref": item["route_ref"],
                        "unchanged": new.model_dump(mode="json") == old,
                        "original_policy": old["policy"],
                        "current_policy": new.policy,
                    }
                )
        result = {"reports": reports, "passed": all(r["unchanged"] for r in reports)}
    elif args.command == "dataset-audit":
        result = audit(read_examples(args.file))
    elif args.command == "dataset-export":
        result = export_training(read_examples(args.file), args.output)
    elif args.command == "serve":
        import uvicorn

        from chemlab.api import create_app

        uvicorn.run(create_app(args.store), host=args.host, port=args.port)
        return 0
    print(canonical_bytes(result).decode("ascii"))
    if isinstance(result, dict) and (
        result.get("state") == "error" or result.get("passed") is False
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
