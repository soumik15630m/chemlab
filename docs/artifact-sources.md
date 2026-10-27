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

## Runtime snapshot

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
