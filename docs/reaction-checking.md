# Reaction and route evidence

Paste `reactants>>product` into **Check a reaction**, or choose **Check every
reaction in this route** on a completed, structurally verified route. A route job
checks every selected occurrence and preserves the original candidate/prediction
bindings. Repeated transformations can share their evidence result; each route
occurrence remains listed. Recent checks survive browser refresh and server
restart. Interrupted jobs remain errors and cannot supply completed reports.

Route findings count every required step occurrence. A contradiction or tool
error cannot be averaged away by supported steps; any remaining unresolved step
keeps the route evidence unresolved. Support on every step still does not prove
experimental compatibility across the route. The separate structural verifier
continues reconstructing root, branches, recurrence and stock membership.
The CLI can replay a completed chemical report against its pinned libraries and
stored raw mapping output without fresh model inference.

The knowledge selection applies to both entry points. Listed-atom checks also run
without a configured knowledge library; missing components remain `not_checked`
or `unknown`. Nothing silently turns them into passes.

## Findings

- Listed atom sources: every represented product heavy element and explicitly
  labelled isotope needs a listed source. An omitted reagent can explain a
  contradiction; this is not a claim of universal chemical impossibility.
- Mapping: RXNMapper proposes atom correspondence. Exact identity-v1 input
  binding, map uniqueness and mapped product element/isotope provenance are
  checked independently. Failed/partial maps cannot supply mapping-dependent
  evidence. Attention confidence is retained only in raw provider output; it is
  not a chemical probability. Oversized model inputs fail without truncation.
- Exact precedent: all product/precursor identities and precursor occurrences
  match an ingested report. Stereo, isotopes, fragments and charge are preserved.
  Duplicate patents/rows retain provenance and are not independent confirmations.
- Context precedent: the pinned public RDChiral extractor gives a local
  transformation context from source mapping. A complete query context must match
  the source context, and replay must recover the exact listed query precursors.
  Remote substrate effects, omitted reagents, selectivity and experimental
  feasibility remain unresolved. This is a structural analogy.

`support`, `contradiction`, `unresolved` and `error` describe these evidence
obligations. They are not chemical confidence tiers. Missing precedent is not a
failed reaction. Stoichiometric balance cannot be inferred from occurrence counts
when coefficients and by-products are absent. Conditions, catalysts, solvents,
temperatures, yields and procedures are outside the requested checking scope.

Existing route acceptance, model checkpoints, stock default, forward top-k and
mapping profiles remain unchanged. No source or model is a chemical authority.

## Sources and reproducibility

The knowledge library uses Daniel Lowe's CC0
[USPTO corpus](https://doi.org/10.6084/m9.figshare.5104873.v1), comprising both
official SMILES archives. Pins are in `configs/reaction-sources/lowe.json`.
Downloads verify exact sizes and SHA-256 hashes; publisher MD5 values are also
recorded. Original expanded source rows, agents and source locations are retained.
The engine does not use the retained agent field to generate/check conditions.
Unsupported CX reaction metadata and invalid inputs are quarantined rather than
silently simplified. These are patent-extracted reports, not independently
verified experimental successes.

The completed source import contains 3,748,190 rows: 1,693,472 admitted represented
rows, including duplicate claims, and 2,054,718 quarantined rows. The source
manifest records 646,284 distinct represented reactions. Of the admitted rows,
90,100 have failed source mapping checks and cannot supply mapping-dependent
contexts. Ingestion does not convert a reported claim into chemical truth.

The completed context build records 1,597,088 extracted contexts, 96,363 unknown
results and 21 extraction timeouts across those admitted rows. It has 181,033
distinct template contexts. Complete manifests and source-bound timeout records
are retained in `evaluation/reports/lowe-source-2026-10-31/`. Unknown/error rows
cannot supply positive context evidence.

Context extraction and replay execute in interruptible Pebble workers. A
10-second dependency deadline is recorded in the evidence policy. Timeouts and
worker crashes remain errors; they cannot become positive evidence. Slow source
chunks are retried per row before any row-level error is recorded. Operational
deadlines can change evidence coverage across machines; published artifacts
record the observed results rather than promising fresh-execution equality.

RXNMapper 0.4.2 uses its bundled ALBERT checkpoint. Weight, tokenizer and execution
pins are in `configs/mapping/rxnmapper.json`; its separate dependencies are in
`requirements-mapping.lock`. The original engine environment keeps its pins.
RDChiral remains 1.1.0. No ChemCensor code, database, generated scores or operational
method is integrated: its published evaluation-only license does not authorize
that use. Dataset labels and scorer-generated fields never enter these indexes.

The unmodified mapper model files also have a Git LFS mirror under
`models/rxnmapper-albert-0.4.2`, with publisher/package provenance in the adjacent
source JSON. Runtime checks validate the package-bundled copy against the same
weight/tokenizer hashes. The engine's selected retrosynthesis and forward
checkpoints are preserved.

Libraries and reports publish completion markers only after hashing their
contents. Evidence sessions check the index bytes before and after a read-only
batch. Row claims and extracted contexts are reconstructed from retained source
rows. Exported evidence includes its policy, input keys, knowledge references and
raw mapping artifact. A source hash establishes identity of bytes, not the truth
of a patent claim.

## Startup and CLI

The standard Docker and native launchers prepare the knowledge library before
starting the application. First use restores the prepared, hash-pinned LFS
archive. Source-development setup without an artifact descriptor downloads the
official archives and builds the source and context indexes; progress is printed.
Later starts validate and reuse complete
snapshots. Partial snapshots are preserved and never selected as completed data.
Docker mounts reaction data read-only in the app and writable in setup. Native
startup uses a second venv for the mapper so its older setuptools requirement
cannot replace the engine's package.

Prepared knowledge archives can be restored after `git lfs pull`; when the pinned
artifact descriptor is present, setup verifies and restores those indexes before
considering a rebuild. Docker keeps indexes in the persistent
`chemlab-reaction-indexes` named volume, read-only in the app. Source downloads and
previous incomplete builds remain separately preserved. Restores verify every
file and publish new directories; they never replace existing data.

The equivalent preparation command inside the supplied Docker runtime is:

```sh
python scripts/setup_reaction_knowledge.py --store var --data /workspace/reaction-data --mapper-python /opt/chemlab-mapper/bin/python
python -m chemlab --store var check-reaction 'CC(=O)Cl.CN>>CNC(C)=O' --knowledge lowe-context-v2
python -m chemlab --store var replay-chemical-check JOB_ID
```

For a different provider or data location, write a `KnowledgeConfig` JSON file and
use `register-reaction-knowledge ALIAS FILE`. This is a trusted local CLI operation;
browser requests cannot install providers or execute arbitrary commands. Mapping
providers use the JSON worker boundary; their architecture/tokenization can change
without changing the engine's identity or evidence contracts.

Every complete check offers a PDF and JSON evidence report plus editable MOL,
SDF, RXN and reaction-SMILES files. Structure exports are reimported and compared
against the original input identities and occurrences. Reports remain separate
from historical route bundles and never overwrite their conclusions.

## Evaluation

`configs/chemical-evaluation/protocol.json` was written before inspecting the
benchmark CSV. The separate Apache-2.0 URSA expert plausibility benchmark contains
1,000 expert-labelled model proposals. It is not an experimental success/failure
dataset. The pinned source yields 814 development inputs and 186 final-reference
inputs, grouped by product constitution only for partitioning. Matching everywhere
else still uses full identity-v1.

`scripts/evaluate_chemical_reference.py` freezes policy, implementation, provider
and data bindings before scoring. The checker receives molecular inputs only.
Human labels and the dataset's generated scorer fields remain outside inference.
Exact final-reference reaction claims cannot supply source/template evidence;
another source's analogy remains eligible and is reported as an analogy. No
final-outcome tuning is permitted. Reports separate support, contradictions,
unknowns, tool errors, coverage and denominators by expert label. The original
14 user-selected routes remain development challenges with route-level labels;
they do not manufacture step-level negatives or estimate population accuracy.

The completed frozen final-reference evaluation has the following outcomes:

| Expert reference | Inputs | Evidence support | Listed-source contradiction | Unresolved | Error |
| --- | ---: | ---: | ---: | ---: | ---: |
| Plausible | 94 | 49 | 0 | 45 | 0 |
| Implausible | 92 | 15 | 16 | 61 | 0 |

Support on 15 expert-implausible proposals demonstrates that local context
matches cannot establish chemical validity. All experimental-feasibility
outcomes remain unresolved. These labels concern expert judgments, not measured
experimental outcomes. Full development/final counts, frozen policy, raw mapping
and source-bound outputs are in
`evaluation/reports/chemical-reference-2026-10-31/`; no final-outcome tuning was
performed. The original route replay in
`evaluation/reports/user-chemical-replay-2026-10-31/` found 4 supported and 18
unresolved distinct reactions. Every one of its 14 routes still has unresolved
steps. It does not identify all the user-labelled incorrect routes.
