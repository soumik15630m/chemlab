from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from chemlab.records import ModelManifest, digest


def content_hash(path: Path | str) -> str:
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        with root.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    entries = []
    for file in sorted(root.rglob("*")):
        if file.is_file():
            entries.append([file.relative_to(root).as_posix(), content_hash(file)])
    return digest(entries)


@runtime_checkable
class PredictionProvider(Protocol):
    def predict(self, effective_input: str, num_results: int) -> list[dict[str, Any]]: ...


def validate_tokenization(tokenizer: Any, smiles: str, max_length: int) -> None:
    tokens = tokenizer.regex.findall(smiles)
    if "".join(tokens) != smiles:
        raise ValueError("unsupported_input: tokenizer discards input characters")
    if any(token not in tokenizer.vocab_dict for token in tokens):
        raise ValueError(
            "unsupported_input: molecule contains tokens outside the checkpoint vocabulary"
        )
    if len(tokens) > max_length:
        raise ValueError("unsupported_input: molecule exceeds the checkpoint sequence limit")


def validate_files(manifest: ModelManifest) -> None:
    if (
        manifest.backend != "replay"
        and content_hash(manifest.checkpoint) != manifest.checkpoint_hash
    ):
        raise ValueError("Checkpoint content changed after registration")
    if manifest.tokenizer_path and content_hash(manifest.tokenizer_path) != manifest.tokenizer_hash:
        raise ValueError("Tokenizer content changed after registration")


class TemplateLibraryProvider:
    def __init__(self, manifest: ModelManifest):
        from rdchiral.initialization import rdchiralReaction

        if manifest.kind != "template_based" or manifest.score_semantics != "cost":
            raise ValueError("Template enumeration requires a template-based cost manifest")
        self.manifest = manifest
        self.templates = [
            (key, rdchiralReaction(manifest.templates[key])) for key in manifest.template_order
        ]

    def predict(self, effective_input: str, num_results: int) -> list[dict[str, Any]]:
        from rdchiral.initialization import rdchiralReactants
        from rdchiral.main import rdchiralRun

        outputs = []
        for template_id, template in self.templates:
            outcomes = sorted(
                rdchiralRun(
                    template, rdchiralReactants(effective_input), **self.manifest.template_settings
                )
            )
            for outcome in outcomes:
                outputs.append(
                    {"precursors": outcome.split("."), "score": 1.0, "template_id": template_id}
                )
        return outputs[:num_results]
