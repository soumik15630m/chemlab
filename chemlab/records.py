from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


def canonical_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True
    ).encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1


class Molecule(Record):
    status: Literal["ok"] = "ok"
    original_smiles: str
    canonical_smiles: str
    identity_policy: Literal["identity-v1"] = "identity-v1"
    mapped_smiles: str | None = None
    unspecified_stereo: bool
    specified_stereo: bool


class MoleculeError(Record):
    status: Literal["parse_error", "unsupported_input"]
    original_smiles: str
    error: str


MoleculeResult = Annotated[Molecule | MoleculeError, Field(discriminator="status")]
Status = Literal["pass", "fail", "unknown", "not_checked", "error", "not_applicable"]
StructuralStatus = Literal["verified", "rejected", "unresolved"]
ForwardStatus = Literal["consistent", "conflict", "incomplete", "not_applicable"]
TerminationReason = Literal[
    "already_in_stock",
    "budget_exhausted",
    "candidate_space_exhausted",
    "requested_route_count_reached",
    "execution_error",
]


class Check(Record):
    name: str
    version: str = "1"
    status: Status
    reason: str
    mandatory: bool = True
    inputs: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    settings: dict[str, Any] = Field(default_factory=dict)


class ModelManifest(Record):
    name: str
    kind: Literal["template_based", "template_free", "forward"]
    backend: Literal["command", "replay", "syntheseus", "python"]
    checkpoint: str
    checkpoint_hash: str
    training_provenance: str
    license: str
    preprocessing: Literal["identity", "remove_stereo"] = "identity"
    supported_atomic_numbers: tuple[int, ...] | None = None
    score_semantics: Literal["probability", "negative_log_cost", "cost"]
    score_direction: Literal["higher", "lower"]
    command: tuple[str, ...] = ()
    model_class: str | None = None
    device: str = "cpu"
    dtype: str = "float32"
    architecture_id: str = "unspecified"
    representation: str = "smiles"
    tokenizer_path: str | None = None
    tokenizer_hash: str | None = None
    provider_version: str = "1"
    determinism: Literal["deterministic", "seeded", "stochastic"] = "deterministic"
    inference_seed: int = 0
    decoding: dict[str, Any] = Field(default_factory=dict)
    templates: dict[str, str] = Field(default_factory=dict)
    template_order: tuple[str, ...] = ()
    template_settings: dict[str, Any] = Field(
        default_factory=lambda: {"combine_enantiomers": False, "keep_mapnums": False}
    )
    replay_file: str | None = None
    timeout_seconds: float = Field(default=120, gt=0)

    @model_validator(mode="after")
    def compatible(self) -> ModelManifest:
        expected = "higher" if self.score_semantics == "probability" else "lower"
        if self.score_direction != expected:
            raise ValueError("Score direction is incompatible with its cost transformation")
        if self.backend == "command" and not self.command:
            raise ValueError("Command backend requires an explicit argv")
        if self.backend == "replay" and not self.replay_file:
            raise ValueError("Replay backend requires a source artifact file")
        if self.backend in ("syntheseus", "python") and not self.model_class:
            raise ValueError("Native backends require a provider class")
        if bool(self.tokenizer_path) != bool(self.tokenizer_hash):
            raise ValueError("Tokenizer path and hash must be supplied together")
        if self.backend == "syntheseus" and self.determinism == "stochastic":
            raise ValueError("Native model caching cannot provide independent stochastic calls")
        if self.kind == "template_based":
            if not self.templates or set(self.template_order) != set(self.templates):
                raise ValueError("Template vocabulary and its exact order are required")
            if len(set(self.template_order)) != len(self.template_order):
                raise ValueError("Template vocabulary has duplicate IDs")
        return self


class Candidate(Record):
    status: Literal["ok"] = "ok"
    index: int = Field(ge=0)
    product: Molecule
    precursors: tuple[Molecule, ...] = Field(min_length=1)
    score: FiniteFloat
    cost: FiniteFloat = Field(ge=0)
    template_id: str | None = None
    mapped_reaction: str | None = None
    mapping_required: bool = False


class CandidateError(Record):
    status: Literal["error"] = "error"
    index: int = Field(ge=0)
    raw: Any
    error: str


CandidateResult = Annotated[Candidate | CandidateError, Field(discriminator="status")]


class Prediction(Record):
    manifest_ref: str
    effective_input: str
    requested_count: int = Field(gt=0)
    raw_output: Any
    candidates: tuple[CandidateResult, ...]
    status: Literal["ok", "error"]
    error: str | None = None
    settings: dict[str, Any]


class Occurrence(Record):
    id: str
    molecule: Molecule


class Step(Record):
    id: str
    product_id: str
    precursor_ids: tuple[str, ...] = Field(min_length=1)
    prediction_ref: str
    candidate_index: int = Field(ge=0)


class Route(Record):
    root_id: str
    molecules: tuple[Occurrence, ...] = Field(min_length=1)
    steps: tuple[Step, ...]
    search_cost: FiniteFloat = Field(ge=0)
    source: str


class Stock(Record):
    name: str
    source: str
    license: str
    identities: tuple[str, ...]


class ForwardEvidence(Record):
    manifest_ref: str
    effective_input: str
    requested_count: int = Field(gt=0)
    products: tuple[MoleculeResult, ...]
    raw_output: Any
    status: Literal["ok", "error"]
    error: str | None = None
    information_lost: bool = False
    settings: dict[str, Any]


class PrecedentSource(Record):
    source_id: str
    product: str
    precursors: tuple[str, ...]
    template_id: str | None = None
    template_smarts: str | None = None
    reference: str | None = None


class Corpus(Record):
    name: str
    version: str
    partition: Literal["training", "development", "final_reference"]
    source: str
    license: str
    multiplicity: Literal["occurrences", "unique"]
    source_artifact_ref: str | None = None
    ingestion_report_ref: str | None = None
    records: tuple[PrecedentSource, ...]


class RunConfig(Record):
    backward_manifest: str
    forward_manifest: str | None
    stock_ref: str
    corpus_ref: str | None = None
    prediction_count: int = Field(gt=0)
    forward_k: int = Field(gt=0)
    logical_expansion_limit: int = Field(gt=0)
    route_limit: int = Field(gt=0)
    max_depth: int = Field(gt=0)
    actual_inference_limit: int | None = Field(default=None, gt=0)
    time_limit_seconds: float | None = Field(default=None, gt=0)
    mapping_profile: Literal["auxiliary", "mapping-required"] = "auxiliary"
    full_diagnostics: bool = False
    seed: int


class VerificationReport(Record):
    route_hash: str
    target: str
    stock_ref: str
    policy: Literal["verification-v1", "verification-v1.1", "verification-v1.2"] = (
        "verification-v1.2"
    )
    mapping_profile: Literal["auxiliary", "mapping-required"]
    structural_status: Literal["verified", "rejected", "unresolved"]
    forward_status: Literal["consistent", "conflict", "incomplete", "not_applicable"]
    checks: tuple[Check, ...]
    mapping_coverage: dict[str, int]
    precedent: dict[str, Any]


class SearchResult(Record):
    routes: tuple[Route, ...]
    termination_reason: Literal[
        "already_in_stock",
        "budget_exhausted",
        "candidate_space_exhausted",
        "requested_route_count_reached",
        "execution_error",
    ]
    exhausted_limit: str | None = None
    candidate_routes_found: int
    duplicate_discoveries: int
    logical_expansions: int
    actual_inferences: int
    cache_hits: int
    prediction_refs: tuple[str, ...] = ()
    error: str | None = None
