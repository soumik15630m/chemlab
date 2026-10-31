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

126 pytest cases pass, including the bounded graph experiment. Ruff checking and
format checking pass; mypy passes for all 27 engine source files. Nineteen named
behavioral mutations are detected. The test client emits one upstream deprecation
warning; no test or check is bypassed for it. Exact versions and source hashes are
recorded in `evaluation/reports/export-validation/validation.json`. The earlier
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

## R011 - Hash-bound reaction challenge replay and scoped observations

Status: computational behavior validated locally; chemical classification not
established. Development data only, not final evaluation.

The user selected three reports and labelled three complete routes correct and
nine incorrect; two remain unlabelled. The portable snapshot retains 64 original
hash-bound objects, 14 routes and 39 step occurrences. Route labels are separate
from observations and supply no invented step labels. Two incorrect-labelled
routes have forward agreement; one correct-labelled route has forward conflict.
These counterexamples do not estimate population accuracy.

Read-only observations preserve represented atom counts, isotope labels and
occurrences, quarantine inapplicable mappings and bound tautomer enumeration.
The pyrazolone case retains its exact-match failure while exposing saved rank-2
and rank-5 representation overlap. Complete enumeration is required for a
non-exact comparison; specified stereo/isotopes are outside that comparison's
scope. Identity-v1, mandatory checks, mapping profiles, checkpoints and search
remain unchanged. No new inference or existing artifact replacement occurred.

Negative result: no element lacks a listed source in these cases, and all 39
steps lack supplied mappings. Inventory checks therefore do not detect the nine
incorrect routes, while bond-edit observations remain unknown. Chemical
assessment remains unresolved. The 22-transformation analysis distinguishes
documented individual reactions from unsupported steps and whole-route labels;
where the precise failing step is not established, it remains unresolved.

Evidence: `evaluation/reports/reaction-challenges-2026-10-28/observations.json`,
`packaged-replay.json`, `final-validation-2/`, and the browser reports. The original
complete bundles and PDF hashes were independently read from a read-only mount;
all 14 packaged diagnostic outputs match the portable challenge replay. The
full suite passes 145 tests, with lint/format/type checks and 25 detected Python
mutants. Six new mutants corrupt counts, mapping applicability, enumeration
completeness, chemical claims, prediction hashes and precedent product identity.
Two separate Chromium
mutants change feasibility wording and route numbers; both fail assertions with
no JavaScript errors. Browser API responses are controlled fixtures, not live
model or vendor validation.

The packaged image reuses the previously validated pinned dependency image and
installs the working-tree package offline. It is not a fresh network dependency
build. Detailed scope, primary-source references and next-stage obligations are
in `docs/reaction-verification-development.md`. A chemical knowledge layer must
validate new claims against independent step-level evidence and untouched cases
before any new acceptance profile is proposed.

## R012 - Provenance-bearing optional stocks and exact unions

Status: complete pinned source ingestion, source replay and software boundaries
validated locally in Docker. No reaction accuracy or benchmark-coverage result.

The optional URSA-BBs import pins upstream revision
`66a64e2e375dde30941770e831ce11ed3db91f55`, original CSV size/SHA-256, dataset-card
SHA-256, source row count and CC BY-NC-SA 4.0 attribution. Original CSV/card bytes,
source IDs and duplicate rows remain in immutable source objects. The validated
255,958-row input yields 255,957 admitted rows and 255,435 unique identity-v1
entries, with 522 duplicate accepted rows and one quarantined row (R013).

Optional provenance fields preserve legacy stock content addresses. The existing
PaRoutes alias was checked against its original hash. Exact unions reconstruct
component membership and retain component license records. Source objects, audits
and parent stocks participate in complete-bundle reference closure. Missing/extra
union members, corrupt sources, malformed records and licence relabelling do not
pass admission. No salt stripping, stereo removal, isotope loss, tautomer merging
or probabilistic/hash-only stock membership was added.

Evidence: `evaluation/reports/stock-integration-2026-10-30/`, including complete
source replay, 163 passing tests, 33 detected Python mutants, packaged-image tests
and live Chromium stock selection. All 11 existing runs, default stock and model
choices are preserved. The source replay is deliberately conservative and takes
minutes on CPU; no optimization equivalence or speed claim is made. Packaging
reuses the pinned dependency image offline, not a fresh network dependency build.

The actual AiZynthFinder public ZINC stock was inspected through remote HDF
metadata: 17,422,831 rows with only the `inchi_key` column. No structures were
invented from those hashes. Its original structure-bearing source is needed for
an exact identity-v1 import. No second planner, checkpoint replacement or model
ensemble was introduced. See `docs/optional-stocks.md` for reproducible commands,
data-license boundaries and the distinction between inventory and chemical validity.

## R013 - URSA-IDV1-001: cyclic canonicalization admission quarantine

Status: observed pinned-dependency behavior with a positive/negative contract
fixture and a detected seeded defect. This is not a chemical invalidity finding.

The first complete-source admission attempt correctly failed because the resulting
stock contained a noncanonical identity. A complete scan isolated source row
223299, `URSA-BB-223298`. Under RDKit package 2026.9.1, applying identity-v1 to
this polycyclic stereo SMILES repeatedly alternates between two strings rather
than reaching a fixed canonical identity. The original, first, second and third
strings are retained in `identity-instability.json` in the R012 report directory.

The importer quarantines that original row with the explicit reason
`identity_v1_not_idempotent_under_pinned_rdkit`; it does not rewrite the stereo,
iterate until an arbitrary result is chosen, patch identity-v1 or drop its source
record. The positive ethanol control still imports. Mutant M33 disables this
admission check and is rejected by the real-source regression fixture. The source
dataset's chemical correctness and the root cause inside RDKit are not established
by this observation. Broader identity-policy or dependency changes require their
own evaluation; this case is handled by explicit input quarantine.

## R014 - CC0 patent claim index with exact represented identities

Implemented an immutable SQLite index of both official Lowe USPTO SMILES archives.
The input is 3,748,190 preserved rows; 1,693,472 are admitted, including duplicate
claims, and 2,054,718 are quarantined (2,054,257 unsupported CX reaction metadata
rows and 461 parse failures). The source manifest records 646,284 distinct
represented reactions. Admitted rows include 90,100 failed source mappings;
those cannot supply mapping-dependent contexts. Source manifest SHA-256 is
`781b4fcdcbd693a69ef38e0934b25483a6227c5ada4969f338d876bd74795250`;
database SHA-256 is
`e5a16da15b1c9b4b79fb96b4cc08629bb3598aef5c0f7e789ca72ffb3aea8914`.
Pins, archive and expanded-file hashes are in `configs/reaction-sources/lowe.json`.

Exact retrieval compares full product and precursor identities after hash
indexing, preserving occurrence multiplicity. Seeded hash collisions do not merge
different lookup results. Raw rows, source locations, duplicates, unsupported
representations and mapping outcomes remain visible. A copied Docker-volume
index was checked byte-for-byte against this manifest; the original remains.
This establishes data/provenance handling, not truth of extracted patent claims
or independence from generator training.

## R015 - Auxiliary mapping with independent input admission

RXNMapper 0.4.2 is isolated from engine dependencies. Its bundled ALBERT weights,
tokenizer and settings are pinned in `configs/mapping/rxnmapper.json`. Raw outputs
are persisted before interpretation; atom correspondence must bind the exact
represented inputs and satisfy map uniqueness and element/isotope provenance.
All 22 distinct original user challenge reactions passed those admission checks.
This is not a reaction-feasibility result or mechanistic validation.

`evaluation/reports/chemical-mapping-2026-10-31-parity.json` records direct upstream
inference parity on three contract cases, including specified stereo, and failure
without truncation for an oversized reaction. Fresh neural inference is not
promised bit-identical across runtimes. Mapper attention confidence is never a
feasibility probability. The isotope observation now includes explicit deuterium
and tritium labels as well as heavy atoms; omitted reagents and unspecified
stoichiometry remain limitations.

The documented Dockerfile was also rebuilt with publisher package downloads.
`evaluation/reports/chemical-dockerfile-2026-10-31/` records matching installed
pins, clean engine/mapper dependency checks, 219 passing contracts, 56 detected
seeded defects and direct upstream mapper parity without a working-tree source
mount. The base OS layer was reused. These are implementation and packaging
checks, not estimates of chemical validity.

## R016 - Context replay cache not promoted

An exact-input extraction replay experiment preserved complete outputs on 128
real source rows and passed mutation/isolation controls. Both canary-bracketed
timing attempts failed the unchanged 10 percent drift gate: observed drift was
79.0 percent, then 12.2 percent on a fixed CPU. Neither run supports a speedup
claim. The experiment is isolated under `chemlab/evaluation/context_replay.py`;
the runtime engine continues using the uncached baseline. Raw measurements and
the unchanged protocol are retained under
`evaluation/reports/context-replay-2026-10-31*/`.

## R017 - Bounded source-derived context evidence

The original full-corpus context extraction stalled on a source reaction. Its
incomplete output is preserved. The replacement uses Pebble 5.2.3 interruptible
processes with a 10-second per-operation bound. A timed-out chunk is retried per
row so healthy neighboring rows do not inherit its timeout. Timed-out or crashed
operations are explicit errors and cannot become evidence support. Worker
termination and subsequent successful recovery have contract tests.

The complete build accounts for all 1,693,472 admitted source rows: 1,597,088
observed contexts, 96,363 unknown results and 21 explicit extraction timeouts.
There are 181,033 distinct template contexts. Its manifest SHA-256 is
`d2b7ea1845c3d71c281d42787f3d7f6d561a19764db9500dc7ccee7b086c2b62`;
the context database SHA-256 is
`2b237cdb31ba6c9ff56266458c51362c1852a446363a8ed968d90ffcfbcc4dcc`.
`evaluation/reports/lowe-source-2026-10-31/final-context-failures.json` retains
all 21 failed rows with their original source binding. The build used six workers;
recorded timeouts are operational observations, not chemical invalidity labels.

The frozen held-out evaluation is recorded in R019. Local template-context
matches are structural analogies; absent conditions, remote substrate effects
and selectivity remain unresolved. The independent evidence service does not
change baseline route acceptance or prune search.

## R018 - Engine admission for URSA-IDV1-001

The R013 cyclic canonicalization counterexample is now rejected at target,
generated-precursor, forward-comparison, custom-stock and verifier admission.
Depiction/exchange endpoints also refuse it rather than producing a picture under
an unstable canonical identity. The low-level observation and the original source
bytes are retained. Identity-v1 canonicalization itself is unchanged; no tautomer,
stereo, salt or fragment equivalence is introduced. Stable positive controls keep
their existing molecular records. This is a narrowly detected dependency defect,
not proof that all RDKit stereo cases are correct.

`evaluation/reports/pretrained-admission-2026-10-31/` records fresh direct/provider
parity for one supported input per unchanged generator and forward checkpoint,
with the original prediction objects retained. It checks that the admission
change preserves those supported cases; it is not exhaustive input coverage.

## R019 - Frozen expert-reference evaluation and unresolved route challenges

Status: completed evaluation with material limitations, not a chemical-validity
achievement. No policy or threshold was tuned on the final outcomes.

The Apache-2.0 URSA reference contains 1,000 expert-labelled model proposals,
not experimental success/failure observations. The previously frozen grouping
produced 814 development and 186 final-reference inputs. Exact final reaction
claims were excluded from source evidence; labels and generated scorer columns
never entered the checker. Protocol hash is
`800c0b9db401581474e5ecf70eb3255c1cce1a54c29f10cfefe4f1d254d9424c`;
checker policy hash is
`f4c6a6cb46ea48ecb96ee4b912cf991a55169dc2ab9a1ea94f9c8dedfb984a3c`.
The implementation/provider/data freeze was written before scoring, with SHA-256
`34ee1d8baac9fca1e1715e3beb188e78626cfb888b22e982387834e1d3641fce`.

| Final-reference expert label | Inputs | Evidence support | Listed-source contradiction | Unresolved | Tool error |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plausible | 94 | 49 | 0 | 45 | 0 |
| Implausible | 92 | 15 | 16 | 61 | 0 |

All 64 supported final inputs received local context support. Fifteen of those
have the expert-implausible label. This directly limits context analogy as a
validity discriminator: it cannot be promoted to a chemical acceptance gate.
The 16 contradictions concern listed atom sources, not universal experimental
impossibility. Development results and complete denominators are retained in
`evaluation/reports/chemical-reference-2026-10-31/`, including original raw
mapping outputs, frozen implementation hashes and source-bound context evidence.
No chemical-feasibility probability or aggregate accuracy claim is introduced.

The original user challenges were independently replayed without passing route
labels to the checker: 22 distinct reactions, 39 occurrences and 14 routes.
Four distinct reactions received source/context support and 18 remained
unresolved. Every complete route retains at least one unresolved step. The
checker did not identify every wrong route, nor did it certify the three
correct-labelled routes. A supported step on an incorrect-labelled route is
not necessarily a wrong step; the labels apply to complete routes only.
Evidence is under `evaluation/reports/user-chemical-replay-2026-10-31/`.
The remaining chemical-validity problem is open research, not a completed oracle.

## R020 - Packaged mapper interpreter and complete-data startup

The first read-only production check completed with a mapper error rather than
support. Setup had resolved the virtual-environment Python symlink to the base
interpreter, losing the mapper's isolated packages. Direct mapper parity and the
native venv test had not exercised that registration boundary. The erroneous
registration and failed check remain retained; they were not rewritten as passes.

Setup now preserves the absolute venv interpreter path. The corrected immutable
registration uses `lowe-context-v2`; the UI prefers it when present. A real symlink
fixture independently asserts the selected interpreter, and mutant M57 replaces
that path handling with the original defect. The full 220-test, 57-mutation,
lint/format/type validation is recorded in
`evaluation/reports/chemical-runtime-fix-2026-10-31/`.
The frozen chemical checker implementation, reference policy and all model/data
artifacts are unchanged by this startup correction.

The complete CC0 knowledge archive is 820,425,621 bytes, SHA-256
`ad253ee09783bf7767ceb4a827c27c30f1027425b8c1d0c71dbe72485a224e2c`.
`evaluation/reports/knowledge-restore-2026-10-31/` records restoration onto an
empty Docker volume without network or rebuilding the corpus. Every source and
context database hash matches the original qualified snapshot. The native
launcher completed with two fresh isolated Linux venvs and pinned cached wheels;
existing model/data files were verified and reused. Windows/macOS native startup
was not executed. See `evaluation/reports/native-startup-2026-10-31/`.

The corrected live Chromium check exercises full-knowledge reaction and saved
route checks, retained history, PDF/JSON/editable downloads and mobile layout:
`evaluation/reports/chemical-production-browser-recovery-2026-10-31/`.
All five pages of the actual saved-route PDF were rendered and reviewed, including
the positive source-citation section. No ChemDraw/Marvin execution is claimed.
`evaluation/reports/chemical-live-preservation-2026-10-31/` confirms all 11
original runs and their 408 bundle/object files remain byte-identical. These
operational checks do not change the unresolved chemical-validity result in R019.

## R021 - Git checkout fidelity for hashed evidence

Generated ASCII-encoded PDFs were initially detected as text by Git. Automatic
line-ending conversion can invalidate PDF offsets and any recorded file hash.
The repository now preserves bytes on checkout and marks PDF, image, archive
and SQLite formats as binary. Existing model and evidence-object LFS rules remain.

`evaluation/reports/git-transport-2026-10-31.json` records real Git checkouts with
`core.autocrlf=true` on a PDF, multiline reference JSON and Python source. All
protected bytes match their original SHA-256 values. Removing the protection in
an isolated temporary repository changes all three hashes, demonstrating detection
of the relevant transport defect. This is artifact/source integrity evidence,
not a chemical research result.

## Evidence and continuation

The chemistry exports add representation and reporting checks, not new chemical
evidence. MOL/SDF and RXN/reaction-SMILES files are reimported with the pinned
RDKit; full identities, participant multiplicities and direction must survive.
Repeated occurrences remain distinct. Fixed PDF metadata and ZIP timestamps
make repeated downloads byte-identical in the pinned runtime. Named mutants
M17-M19 remove stereo, reverse reaction direction and hide fixture disclosure;
the contract tests detect all three. The real saved run exports two routes and
retains its exact public precedent citation. Report layout is reviewed from
rendered pages. Chromium exercises attachment bytes and desktop/mobile controls;
this caught and corrected a blur/change event that replaced a clicked link.
An additional browser mutation points the PDF control at the SVG endpoint; the
download test rejects it without a JavaScript/setup error. This is separate from
the nineteen Python mutants. Evidence is under
`evaluation/reports/export-validation/`. The packaged image is tested without a
working-tree mount under `evaluation/reports/export-image-validation/`. Recovery
reuses cached dependencies after checking all 84 pinned versions and `pip check`;
the slow fresh network build was cancelled and is not claimed as completed.
ChemDraw and Marvin
have not been executed: interoperability claims are limited to documented
exchange-format support and RDKit roundtrips. No experimental feasibility,
reaction conditions or optimized 3D geometries are claimed.

The LFS distribution adds operational snapshot checks, not a chemistry result.
The frozen archive contains 39 registered artifacts and seven complete runs.
An online SQLite backup fixes the database view; immutable objects and complete
bundles are validated before ZIP publication. Restore checks the manifest,
per-file hashes, database integrity and bundle bindings before publishing into a
new directory. Tests cover corruption, unsafe paths, active runs, existing state
and undownloaded LFS pointers. Named mutants M15 and M16 test byte preservation
and LFS admission. Original model/data bytes and provenance are preserved.

Remote distribution is confirmed in
`evaluation/reports/lfs-distribution/release-distribution.json`: the standard
client acknowledged all twelve LFS objects, and eight files downloaded into a
fresh GitHub clone matched their sizes and SHA-256 hashes. The four largest
objects were not independently redownloaded in that clone. A user-approved
disposable Docker job uploaded the last checkpoint after checking the original
publisher archive and checkpoint hashes. The one-off workflow was disabled after
success; its isolated branch and run remain audit evidence. Repeated local DNS
failures are an operational limitation, not a change to verification policy.

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
