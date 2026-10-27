# Research ledger

This is an ongoing engineering and research record. A passing computational
experiment is not experimental validation of chemistry. Entries distinguish
proposed, tested locally, promoted and unsuccessful results. Do not call an
existing technique a new discovery.

## R001 - Independently replayable route certificates

Status: promoted to v1 after local Docker validation, 27 October 2026.

Hypothesis: a route bundle with original provider records, immutable input
references, deterministic check results and file hashes permits independent
reconstruction and exposes export/evidence corruption.

Implementation: `chemlab/verification/verifier.py`,
`chemlab/reporting/bundles.py`, `tests/test_infrastructure.py`.

Acceptance: a valid alternative route passes; replaced/dropped precursors,
wrong targets, ancestor recurrence, shared occurrences, stale evidence and
corrupt publication fail or remain unresolved according to the contract.
Reverification must reproduce the exact report from the same stored evidence.
Interrupted publication must expose no complete result.

Scope: computational structure and provenance. This is inspired by small
independent checkers; the certificate is not a formal proof of chemistry.

Evidence: `evaluation/reports/release-acceptance/validation.json` and its JUnit report.
Real-model routes and exact replay are recorded in
`evaluation/reports/precedent-integration.json` and
`evaluation/reports/precedent-replay.json`. Older reports remain immutable. During
development, replay correctly exposed a changed check set; the verifier policy
was versioned rather than overwriting earlier reports. The active policy is
verification-v1.2 (including score reconstruction and disconnected-fragment
mapping binding).

## R002 - Mutation-sensitive contract tests

Status: ten named mutants detected in local Docker validation.

Hypothesis: tests derived from explicit expected behavior detect plausible
defects rather than merely reproducing implementation decisions.

Method: first require an unmodified passing baseline. In disposable copies,
seed isolated changes to identity preservation, cycle checks, dependency
completeness, score direction, status aggregation, cache integrity and expansion
accounting. Run the relevant tests and record assertion failures separately
from setup/import errors. A broken import is not a killed behavioral mutant.

Acceptance: every named non-equivalent mutant must fail an appropriate test.
Survivors remain visible and require a stronger test or a documented equivalent
mutation analysis. Mutation detection does not establish complete correctness.

Evidence: `evaluation/reports/release-acceptance/mutation-report.json`. All ten mutants
produced assertion failures with zero setup errors. The unmodified baseline
passed. This is a deliberately scoped mutation set, not exhaustive coverage.

## R003 - Bounded graph-contract conformance

Status: 1,572 bounded cases passed in local Docker validation.

Hypothesis: the occurrence-tree verifier agrees with an independently formulated
graph oracle over a fully enumerated small domain.

Method: enumerate directed graphs with one to three molecule occurrences,
including self-edges, disconnected components, cycles and shared children.
Repeat with distinct and repeated chemical identities. Compare the verifier's
graph decision with NetworkX arborescence/reachability plus an independent
ancestor-identity predicate.

Scope: exhaustive only over the declared finite domain. This is not an
unbounded formal proof or an evaluation of chemical feasibility.

Evidence: `tests/test_bounded_graphs.py` and the source-bound acceptance report.
The case count includes selected identity labelings over every directed graph
with one to three occurrences; it is not a claim about all molecular graphs.

## R004 - Counterexample-guided search feedback

Status: research proposal; not a new baseline pruning policy.

Transfer the generate/check/counterexample pattern from program synthesis.
Return a precise witnessed violation and its exact input binding. Reuse proven
structural exclusions only within their scope. A forward-model disagreement is
not a proof of chemical impossibility and must not become a universal rule.

Reference: Armando Solar-Lezama, Introduction to Program Synthesis, Lecture 10:
https://people.csail.mit.edu/asolar/SynthesisCourse2020/Lecture10.htm

Promotion requires equivalence to baseline route identities and structural
decisions at equal logical budgets, with explicit evaluation of any intended
coverage changes. No reviewer-feedback training is enabled by this proposal.

## R005 - Chemical verifier stress testing across sources

Status: research proposal; external dataset not yet integrated.

Evaluate chemically plausible mistakes as well as valid alternatives. Separate
model proposals, edited recorded reactions and other candidate sources instead
of reporting only an aggregate accuracy. Keep false acceptance and false
rejection denominators explicit. Failed experimental records do not establish
universal infeasibility under every possible condition.

Reference: Yu et al., FREA: A Multi-Source Expert Benchmark for Reaction
Feasibility Verification, 2026, ongoing-work preprint:
https://arxiv.org/abs/2610.06614

## R006 - Selective prediction with controlled risk

Status: research proposal; excluded from acceptance/ranking decisions.

Investigate abstention calibrated on an independent labeled set. State the
specific statistical guarantee, calibration procedure and distributional
assumptions before implementation. Do not convert a population risk bound into
a guarantee about one reaction, or reuse a calibration set as final evaluation.

Reference: Bai and Jin, Conformal Selective Prediction with General Risk
Control, 2026 preprint: https://arxiv.org/abs/2603.24704

## R007 - Replaceable generator with independently configured pretrained checking

Status: provider boundary and real-model integration validated locally in Docker.

Implementation: provider SDK, immutable registry/manifests, Python/command/native
adapters and separate forward evidence. A deterministic template-library provider
exercises the same boundary without learned inference. A custom provider can use
its own tokenizer or graph architecture while emitting the common reaction
contract. Checkpoint and tokenizer hashes bind outputs to their source artifacts.

Acceptance: direct/provider parity, score-direction/duplicate fixtures,
checkpoint-change rejection, deterministic replay and end-to-end execution.
Pretrained agreement is evidence, not an independent chemical oracle; public
generator and checker training data may overlap.

Evidence: `evaluation/reports/pretrained-parity.json` records one direct/provider
input per real model, both passing. `evaluation/reports/v1-real-inference.json`
records fresh real inference; subsequent integration reports exercise valid cache
reuse at the same logical expansion budget. Two candidate routes were structurally
verified and forward-consistent in this smoke case. This is not a benchmark of
chemical accuracy or a demonstration of general reliability.

## R008 - Stable search ordering across process hash seeds

Status: promoted to v1 after local Docker validation.

Adaptation: stable precursor/node ordering and exact rational accumulation during
route extraction. See `docs/dependency-adaptations.md`. The pinned upstream API
was inspected rather than assumed deterministic.

Evidence: `tests/test_determinism.py` runs a fixed budgeted fixture in three fresh
processes with different Python hash seeds and requires the same explicitly
expected expansions and result. This covers that fixture and does not establish
cross-device neural determinism.

## R009 - Lossless tokenizer admission

Status: promoted for the selected native checkpoint interface after local tests.

The adapter checks complete character coverage, vocabulary membership and sequence
length before native inference. Unknown isotopic tokens, discarded characters
and excessive lengths fail visibly. No unknown token is silently treated as the
requested structure. Noncanonical/nonfinite outputs are preserved as explicit
error representations rather than fabricated successful predictions.

Evidence: `tests/test_plugins.py`, `tests/test_adapters.py`, and the acceptance
report. Other model/tokenizer interfaces still need their own admission fixtures.

## Interface validation

`evaluation/reports/release-browser.json` records a passing Chromium desktop/mobile
smoke test with zero JavaScript errors. The first mobile run failed on long
molecule text overflowing the layout; the layout was corrected and rechecked.
This is UI validation, not a chemistry research result.

## Current acceptance result

111 pytest cases pass, including the bounded graph experiment. Ruff checking and
format checking pass; mypy passes for all 25 engine source files. Sixteen named
behavioral mutations are detected. The test client emits one upstream deprecation
warning; no test or check is bypassed for it. Exact versions and source hashes are
recorded in `evaluation/reports/lfs-distribution/validation.json`. The earlier
release acceptance reports retain their original source hashes and counts.

The default public corpus contains 40,008 OpenRetro USPTO-50K training reactions.
Chemical verifier precision/recall, FREA integration, calibration, a custom trained model and broader
PaRoutes benchmark measurements remain future research, with no claimed results.

## R010 - Public precedent with byte-verified source provenance

Status: integrated and validated locally in Docker.

Source: the public OpenRetro USPTO-50K training CSV, Git blob
`7f5f61c901d637061dc77ab785e570d9c0d14c22`. Original source bytes, source IDs,
mapping strings, multiplicity policy, ingestion audit and SHA-256 are retained.
40,008 input records were accepted under the declared representation, with zero
quarantined records. Validation/test splits were not downloaded for guidance.

Evidence: `evaluation/reports/public-corpus.json`,
`evaluation/reports/public-corpus-retrieval.json`,
`evaluation/reports/precedent-integration.json` and
`evaluation/reports/precedent-replay.json`. A positive control recovered the
explicitly expected `US05849732:train-row-1`. The real-route smoke case recovered
one exact represented transformation shared by both routes, linked to
`US20050148627A1:train-row-15`. Other proposed steps had no exact match; this absence
remains visible and is not interpreted as chemical impossibility. Source artifacts
are included in complete bundles, and report replay matched exactly.

The repository declares MIT for its code; a separate underlying dataset license
was not specified in the inspected source. This distinction is retained in the
corpus metadata. Overlap with pretrained models and future PaRoutes evaluations
has not been audited, so this is not purportedly independent evidence or a final
benchmark result. These records document reported reactions, not guaranteed
experimental success.

## Evidence policy

The LFS distribution adds operational snapshot checks, not a chemistry result.
The frozen archive contains 39 registered artifacts and seven complete runs.
An online SQLite backup fixes the database view; immutable objects and complete
bundles are validated before ZIP publication. Restore checks the manifest,
per-file hashes, database integrity and bundle bindings before publishing into a
new directory. Tests cover corruption, unsafe paths, active runs, existing state
and undownloaded LFS pointers. Named mutants M15 and M16 test byte preservation
and LFS admission. Original model/data bytes and provenance are preserved.

Startup validation is operational evidence, not a chemistry research result.
`evaluation/reports/startup-acceptance/native-startup.json` records a new isolated
Linux Python 3.11 venv, pinned CPU dependencies, 40,008 registered public records,
SVG rendering and two real-model structurally verified/forward-consistent routes.
`compose-startup.json` records the corresponding Compose service checks;
`compose-failure.json` records an injected setup exit 17 that prevented application
startup. The models/data were already downloaded and reused. Windows/macOS native
startup was not executed. The built image also passed the complete 101-test,
14-mutation suite without a working-tree mount; its source hashes are retained in
`evaluation/reports/startup-image-acceptance/validation.json`.

Write reproducible test/experiment reports under `evaluation/reports/`. A promoted
entry must cite its report, source version/hash, exact domain and limitations.
Failed experiments and unsupported claims must remain distinguishable from
successful local validation. New claims need new experiments.
