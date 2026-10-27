# ChemLab architecture

This revision records the user's decisions after the original architecture
specification. The original specification still defines identity-v1, check
statuses, the occurrence-tree contract and verification/evidence requirements.
Where scope differs, this revision takes precedence.

## Product

Input: a target molecule. Output: multiple candidate synthesis routes, with
starting materials, reactants/products for every step, evidence and uncertainties.
Reaction conditions, quantities, yields and experimental procedures are outside v1.
The configured stock snapshot is the default stopping criterion; a user can
provide a different inventory. Snapshot membership is not live availability.

## Responsibility

Correctness has priority over inference speed and every other optimization.
Prefer deterministic algorithms wherever possible. A model is the least
load-bearing component: it proposes single-step reactions or ranks expansions.
It never supplies a whole route that is accepted without reconstruction.

The engine has an explicit acceptance contract. Inputs are adapted to this
contract; the engine never weakens it to accommodate a model or dependency.
Every accepted route must satisfy all mandatory invariants. Missing, unsupported,
indeterminate or failed mandatory operations cannot produce acceptance. This
guarantee concerns computational structure and evidence binding, not experimental
success. Tests and mutation checks are evidence about the implementation, not a
formal proof that arbitrary software has no defects.

The search engine repeatedly expands intermediates and constructs routes. Use
the pinned Syntheseus Retro* baseline, with tree occurrences and ancestor-cycle
prevention. Do not silently substitute MCTS or call Retro* MCTS. Additional
search algorithms require explicit comparative evaluation.

The independent verifier owns structural decisions. It reconstructs every route
and binds steps to original provider output. Forward prediction is supporting
evidence; disagreement never prunes baseline search. Exact public precedent is
separate evidence. Neither model agreement nor a template proves experimental
feasibility. Chemistry has no complete legal-move oracle equivalent to chess.

## Replaceable generation, separate checking

The generator slot accepts a registered provider with a versioned manifest.
Its internal representation can be SMILES, tokens, graphs or a custom format.
The external contract remains decoded product/precursor SMILES, original
precursor occurrences, finite scores with declared meaning, and optional
template IDs/mapping. Raw output is persisted before planner deduplication.

Python providers load once per worker. Command providers provide an isolated
JSON interface for incompatible runtimes. Native Syntheseus providers use the
public model call path. A deterministic template-library provider can enumerate
declared transformations without a learned model. Providers run separately;
there is no implicit ensemble or score mixing.

Custom model training is a later phase. Current infrastructure provides provider
registration, checkpoint/tokenizer/architecture binding, parity evaluation and
partitioned dataset export. It does not pretend to train a model without a chosen
architecture and suitable data. Until custom weights exist, a pretrained
generator can occupy the same slot for real end-to-end runs.

The checker has its own manifest/checkpoint and frozen requested top-k. The
initial real-model integration uses the standalone RetroChimeraDeNovo generator
and ForwardChimeraDeNovo checker, not the RetroChimera ensemble. Both are trained
on Pistachio and have potentially correlated errors; agreement is not independent
confirmation. Their official Figshare checkpoint pages declare MIT licenses.

## Determinism

Identity, graph checks, route signatures, exact retrieval and status aggregation
are deterministic for pinned inputs, policies and software versions. Stable
ordering is explicit. Logical expansion attempts count framework cache hits.
Operational time limits can alter coverage and are recorded separately.

Provider manifests bind checkpoint and tokenizer content, architecture, runtime,
dtype, decoding, seed and determinism policy. Seeded neural calls reset and restore
RNG state under a process lock. Unsupported deterministic execution fails visibly.
Stored predictions support deterministic replay; fresh inference is not promised
bit-identical across devices or software versions. Stochastic requests cannot
silently reuse one realization when independent sampling is required.

## Entry points and persistence

A local web workspace and CLI use the same application service. SQLite tracks
immutable object references, cache entries, registered providers and run state.
Content-addressed files preserve source data. Publication stages and validates
a complete bundle, then atomically exposes it. Interrupted output stays incomplete.

Model registration and executable provider configuration are trusted local CLI
operations. The browser can choose registered models and submit molecules; it
cannot install code or run arbitrary commands. The server binds to loopback.

## Acceptance

Contract fixtures include valid routes, corrupt exports, molecular recurrence,
shared intermediates, missing AND precursors, mapping profiles, stereo conflicts,
source binding, score direction, corrupt caches and interrupted publication.
Mutation checks must demonstrate that tests catch plausible implementation
defects. Final evaluation partitions are excluded from generation and evidence.
No passing software suite establishes experimental chemical feasibility.
