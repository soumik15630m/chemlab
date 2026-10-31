# Optional building-block stocks

## URSA-BBs

The [URSA-BBs dataset card](https://huggingface.co/datasets/insilicomedicine/URSA-BBs/blob/66a64e2e375dde30941770e831ce11ed3db91f55/README.md)
describes 255,958 building-block structures with internal IDs, derived from
ASKCOS buyables and checked against eMolecules by its publishers. It supplies no
supplier IDs, prices, quantities or live availability information. Dataset terms
are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), separate
from ChemLab's Apache-2.0 source license. The pinned dataset card and attribution
are retained with the imported source. Use of the data is subject to its terms.

`configs/stocks/ursa-bbs-v1.json` fixes the repository revision, CSV/card hashes,
byte size, row count and license metadata. Downloading does not follow `main`.
Existing matching downloads are reused; inconsistent existing files are preserved
and rejected. Interrupted or corrupt downloads cannot become completed files.

Import after preparing the normal application environment. In Docker:

```sh
docker compose run --rm --no-deps --entrypoint python chemlab -m scripts.import_optional_stock --store /workspace/var --downloads /workspace/var/stock-downloads
```

In the native environment, from the repository root:

```powershell
.venv/Scripts/python.exe -m scripts.import_optional_stock --store var/local
```

On POSIX use `.venv/bin/python` in place of `.venv/Scripts/python.exe`. The alias
is `ursa-bbs-v1-identity-v1`. Reload the app registry and explicitly choose that
stock in the starting-material selector. These commands add an optional snapshot;
the bootstrap configuration and existing run configurations are not rewritten.
The optional raw downloads and mutable state stay under ignored `var/` paths;
they are not added to the frozen runtime-v1 archive or the Apache-licensed source.

## Identity and ingestion audit

The CSV importer preserves every original row, ID and duplicate in a hash-bound
source artifact. Full identity-v1 strings decide equality; stereo, isotope labels,
charge and disconnected fragments are retained. Canonical duplicates become one
availability identity while their source rows remain recoverable. Invalid or
unsupported rows are quarantined with their original contents and reasons.
Malformed CSV structure, duplicate/missing source IDs, wrong hashes, wrong byte
sizes and wrong source row counts reject the import.

Source row 223299 (`URSA-BB-223298`) exposes a canonical SMILES cycle in the pinned
RDKit 2026.9.1 runtime. Repeated application of identity-v1 alternates between two
strings. It is quarantined as `identity_v1_not_idempotent_under_pinned_rdkit`; the
stereo specification is not edited or collapsed. This is an observed representation
failure at our boundary, not a claim that the source molecule is chemically invalid.
The source ID, original string and three canonicalization results are preserved in
`evaluation/reports/stock-integration-2026-10-30/identity-instability.json`.

The resulting stock is an identity-v1-derived snapshot, not a claim to reproduce
the paper's exact benchmark stock or evaluation protocol. No frozen evaluation
stock has been replaced. Record its stock reference and ingestion report when
using it in an experiment. Registration stores source/card bytes and the full
audit; loading replays ingestion, and complete route bundles include this lineage.
The validated conversion admits 255,957 source rows, representing 255,435 unique
identities; 522 accepted rows duplicate another full identity, and one row is
quarantined. Import and provenance replay can take minutes on CPU.

## Exact unions

Registered full-identity snapshots can be combined explicitly:

```sh
docker compose run --rm --no-deps chemlab merge-stocks my-combined-stock-v1 paroutes-n1-v2 ursa-bbs-v1-identity-v1
```

This example is a PaRoutes/URSA development union; it is not Sriram's exact mix.
Native equivalent: `python -m chemlab --store var/local merge-stocks` followed by
the same arguments, using the prepared venv interpreter. Choose a new alias for a
different union. Existing aliases and source stocks are immutable.

Union equality is full canonical identity, including stereo, charge, isotopes
and fragments. Component references and their distinct license records are
retained, validated and included in complete bundles. Missing or extra union
members and relabelled component terms are rejected. A union does not assert
current supplier availability or independent evidence from overlapping catalogues.

## AiZynthFinder sources

The [stock documentation](https://molecularai.github.io/aizynthfinder/stocks.html)
and [configuration documentation](https://molecularai.github.io/aizynthfinder/configuration.html)
describe InChIKey-based stocks. The public downloader at upstream commit
`21ff546d5f22331b078390a2f12dc04defc3f39c` selects `zinc_stock.hdf5` from
`https://ndownloader.figshare.com/files/23086469`; its standard reader loads the
`inchi_key` column. A key-only index is insufficient to reconstruct original
structures and prove identity-v1 membership. Bloom-filter hits likewise cannot
establish exact membership by themselves.

Remote HDF metadata inspection of that actual file found 17,422,831 rows and the
single column `inchi_key`. No full file download or SMILES recovery was claimed.
The inspection is recorded in
`evaluation/reports/stock-integration-2026-10-30/aizynth-stock-format.json`.

To reproduce a particular mixed stock, retain the original SMILES-bearing source
snapshot, source identifiers and data terms. That source can be imported using a
pinned `StockCSVSpec` and combined with URSA. An InChIKey must not be promoted to a
full identity or used to declare a terminal available without confirming structure
data. AiZynthFinder's stock format, policy model and planner are separate choices;
this integration does not add a second planner or change selected checkpoints.

The associated [URSA paper](https://arxiv.org/html/2607.04688v1) distinguishes stock
termination from reaction-level chemical plausibility. A larger inventory changes
which terminals can be reached; it does not establish that the reactions are valid
or demonstrate that a model became more accurate. Model comparisons need the same
stock and fixed budgets. No model accuracy or search-coverage improvement is
claimed by this importer.
