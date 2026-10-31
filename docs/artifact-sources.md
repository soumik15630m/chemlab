# Downloaded artifacts

`models/` and `artifacts/runtime-v1.zip` are stored using Git LFS. The original
files are retained, including the publisher archives. `artifacts/downloads.json`
records SHA-256 values and byte sizes; the runtime ZIP also carries a per-file
manifest. Git LFS validates downloaded content against its SHA-256 object ID.

## Pretrained models

Publisher/author listed by both official records: Krzysztof Maziarz.

- RetroChimeraDeNovo (Pistachio), Figshare version 1,
  DOI `10.6084/m9.figshare.31150195.v1`:
  https://figshare.com/articles/software/RetroChimeraDeNovo_Pistachio_/31150195
- ForwardChimeraDeNovo (Pistachio), Figshare version 1,
  DOI `10.6084/m9.figshare.32994914.v1`:
  https://figshare.com/articles/software/ForwardChimeraDeNovo_Pistachio_/32994914

Both publisher records label the checkpoints MIT and link to
https://opensource.org/licenses/MIT. The verbatim publisher metadata is retained
in `models/generator-source.json` and `models/checker-source.json`. These are
upstream checkpoints; ChemLab does not claim authorship or ownership. The original
ZIPs, extracted weights and tokenizer vocabulary bytes have not been modified.

Both models were trained on Pistachio. Their agreement is correlated evidence,
not independent experimental confirmation. Training/evaluation overlap remains
unaudited. A checkpoint license does not provide access to its training corpus.

## Stock and reaction sources

- PaRoutes v2 n1 stock, Zenodo record 7341155:
  https://zenodo.org/records/7341155, CC-BY-4.0.
  The original stock file is retained as `models/paroutes-n1-stock.txt`.
- OpenRetro USPTO-50K raw training split:
  https://github.com/coleygroup/openretro/blob/main/data/USPTO_50k/raw/raw_train.csv.
  The retained Git blob is `7f5f61c901d637061dc77ab785e570d9c0d14c22`.
  `models/openretro-train-source.json` retains source URLs and provenance, and
  `models/openretro-train.csv` retains the original bytes.

The OpenRetro repository labels its code MIT; a separate underlying dataset
license was not specified in the inspected source. ChemLab does not relabel the
dataset MIT or imply that it is independent confirmation. The runtime corpus
records the representation/ingestion policy and the source patent references.
Stock is benchmark availability, not a current supplier offer. No validation/test
split has been added to search guidance.

## Optional stock imports

Optional URSA-BBs ingestion is documented in [optional stocks](optional-stocks.md).
The pinned source is Hugging Face revision
`66a64e2e375dde30941770e831ce11ed3db91f55`, CSV SHA-256
`b895120f2b80a75e9208b969dd6d4d453196bda231649824f9a5d33bb53ad3e6`.
It is CC BY-NC-SA 4.0 and retains the publisher's card and attribution in the
registered source. It is not included in the frozen runtime-v1 snapshot, and it
is not relabelled Apache-2.0. Stock availability and reaction validity remain
separate assessments.

## Reaction knowledge additions

Daniel Lowe's USPTO 1976-Sep2016 SMILES archives are CC0-1.0, pinned by DOI,
publisher file IDs and checksums in `configs/reaction-sources/lowe.json`:
https://doi.org/10.6084/m9.figshare.5104873.v1. Derived indexes preserve original
rows and quarantine unsupported representations; extraction does not certify a
reaction. The prepared source/context indexes are distributed separately as
`artifacts/reaction-knowledge-v1.zip`, pinned by
`configs/reaction-sources/knowledge-artifact.json`. Normal setup verifies and
restores that archive. Source-development setup without the descriptor downloads
the original publisher files and builds the indexes. The original runtime-v1
archive remains unchanged.

RXNMapper 0.4.2 and its bundled ALBERT mapping model are MIT:
https://github.com/rxn4chemistry/rxnmapper. Exact model/tokenizer hashes are in
`configs/mapping/rxnmapper.json`. RDChiral 1.1.0 is MIT:
https://github.com/connorcoley/rdchiral. Their outputs are independently checked at
the boundary and are not treated as chemical authorities.
The original mapper license is retained as
`models/rxnmapper-albert-0.4.2-LICENSE`. Additional download sizes and hashes are
listed in `artifacts/reaction-downloads-v1.json`; every mirrored model file is
checked against the pinned installed publisher distribution.

The URSA expert plausibility CSV is a separate Apache-2.0 reference dataset:
https://huggingface.co/datasets/insilicomedicine/URSA-benchmarking-sets.
Revision and Git blob are frozen in `configs/chemical-evaluation/protocol.json`.
Only expert labels are used for evaluation; neither labels nor generated scorer
columns enter operational knowledge or checker features. ChemCensor itself has
an evaluation-only license and is not integrated.

Archive handling adds py7zr 1.1.4, LGPL-2.1-or-later, with its own transitive
package licenses. Installed distributions retain their upstream notices. These
terms are separate from ChemLab's Apache-2.0 code license.
Pebble 5.2.3 supplies interruptible worker processes and retains its LGPL terms:
https://github.com/noxdafox/pebble.

## Original runtime snapshot

`artifacts/runtime-v1.zip` contains a consistent SQLite backup, registered
content-addressed objects, prediction/cache references and the complete bundles
for seven historical runs. Public source records in those bundles retain the
above provenance and licensing limitations. Per-file hashes, database integrity
and bundle bindings are checked before publication and restore.

The live database, transient locks, WAL/shared-memory files, incomplete runs,
venvs, local agent instructions and credentials are excluded. The snapshot keeps
its original Docker model/bundle paths and original verification policy labels.
It is neither proof of experimental feasibility nor an automatically trusted
cache for a different environment. Restore never replaces existing runtime data.
