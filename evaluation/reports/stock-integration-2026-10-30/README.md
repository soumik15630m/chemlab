# Optional stock integration, 30 October 2026

Scope: pinned data ingestion, identity/provenance boundaries and optional stock
selection. No new chemical feasibility, model accuracy or search-coverage claim.

## Source and admission

URSA-BBs revision `66a64e2e375dde30941770e831ce11ed3db91f55`, CSV SHA-256
`b895120f2b80a75e9208b969dd6d4d453196bda231649824f9a5d33bb53ad3e6`,
10,955,751 bytes, 255,958 original rows. The pinned source/card metadata and
CC BY-NC-SA 4.0 attribution are in `configs/stocks/ursa-bbs-v1.json`.

- `initial-source-validation.json`: the first isolated attempt failed stock
  admission on a noncanonical identity. It was not registered in live state.
- `identity-instability.json`: a complete scan found one source row whose
  identity-v1 canonicalization cycles under the pinned RDKit runtime. This is
  URSA-IDV1-001 / `URSA-BB-223298`, row 223299. Original and successive strings
  are retained; the molecule is not declared chemically invalid.
- `ursa-source-validation.json`: the corrected input-admission policy retains
  every source row and quarantines that entry. 255,957 admitted rows produce
  255,435 full identities, with 522 duplicate admitted rows. The whole source was
  independently replayed and existing PaRoutes stock serialization/hash checked.
  The single import-plus-replay operation took about 337 seconds in this local
  container; that is an operational observation, not an optimization benchmark.
- `registration-output.json`: the documented importer registered the same stock,
  source and audit hashes in live state under `ursa-bbs-v1-identity-v1`.

Stock: `dc0dfc4f80d0fd42ec9839a28cf0ecd7348941a202323154f56f9ce3e7c393da`.
Source: `e331b95bbb6edfb6545ef97a0729f377c8a3a1b53ff22a85d6cbbb757c162e25`.
Audit: `86795fb39f8283f34e83c7487af5b0bf58241c52effac1a0930a53e22bd2d89f`.

## Software and deployment evidence

- `validation/`: lint, formatting and mypy pass; 163 tests pass with zero failures,
  errors or skips. All 33 named Python mutants are detected. Eight new mutations
  corrupt source/download integrity, union completeness, fragments, legacy
  serialization, bundle closure, source-ID uniqueness and idempotence admission.
- `packaged-stock-tests.xml`: 30 stock/startup tests pass from the built image
  without a working-tree mount.
- `local-stock-browser.json`, `stock-desktop.png`, `stock-mobile.png`: real local
  API and Chromium selection checks. URSA is selectable, PaRoutes remains the
  initial default, model selections are unchanged, all 11 saved runs remain and
  no JavaScript errors/mobile horizontal overflow were detected. No new synthesis
  or model inference was requested.
- `runtime-provenance.json`: all 84 dependency pins match, `pip check` passes and
  70 packaged source/test/script/config files match the working tree. The package
  was installed offline over the previously validated dependency image. A fresh
  network dependency build is not claimed.

## AiZynthFinder boundary

`aizynth-stock-format.json` records remote HDF metadata inspection of the exact
public stock selected by the upstream downloader at commit
`21ff546d5f22331b078390a2f12dc04defc3f39c`. Its single column is `inchi_key`, with
17,422,831 rows. HTTP ranges were used; no full file hash or structure recovery is
claimed. No AiZynthFinder stock was admitted, model replaced or second planner
added. Original SMILES-bearing data is needed to reproduce a full-identity mixed
stock. Exact unions of registered full-identity sources are implemented and tested.

See `docs/optional-stocks.md` for commands and limitations. The included frozen
runtime-v1 archive, model/checkpoint artifacts, identity-v1 and existing evaluation
settings remain unchanged.
