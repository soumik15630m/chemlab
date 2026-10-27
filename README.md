# ChemLab

Enter a target molecule and explore candidate synthesis routes. Inspect the
starting materials, every reaction step, structural checks, forward consistency
and available public precedent. Model proposals are untrusted inputs.

V1 omits reaction conditions and experimental procedures. A structurally verified
route is not a promise of experimental success. Conflicting/incomplete evidence
is retained and displayed separately.

## Clone and download models/data

Install Git and Git LFS, then clone and materialize the large files:

```sh
git lfs install
git clone https://github.com/soumik15630m/chemlab.git
cd chemlab
git lfs pull
```

The clone normally downloads LFS files automatically; `git lfs pull` also handles
a clone made with smudging disabled. The download includes both pretrained
checkpoints, tokenizers, original publisher ZIPs, stock and public precedent data
(about 3.3 GB together), plus `artifacts/runtime-v1.zip` (about 13.4 MB).
`artifacts/downloads.json` lists exact sizes and SHA-256 hashes. Use `git lfs pull`
to ensure the payloads are present, rather than relying on source archive settings.
Individual downloads: [generator weights](models/generator/combined.ckpt),
[checker weights](models/checker/combined.ckpt) and
[frozen runtime snapshot](artifacts/runtime-v1.zip).
Undownloaded LFS pointer files are rejected during startup with a recovery message.
See `docs/artifact-sources.md` for attribution, licenses and data limitations.

After downloading, choose Docker or the native venv below. Both launchers reuse
the materialized model/data files. Runtime history restoration is optional.

## Start with Docker

Install Docker Desktop (Linux containers) or Docker Engine with Compose v2 or
newer, start it, and run this from the checkout:

```sh
docker compose up --build
```

Open [ChemLab](http://127.0.0.1:8080) once the application reports it is running.
Compose builds the pinned Python 3.11 CPU environment, reuses or downloads the
models and public data, validates/registers them, and starts the web app. Setup failure
prevents the app from starting. No host Python installation is required.

The optional convenience script does the same thing:

```sh
python start_docker.py
python start_docker.py --detach --port 8081
```

The script needs Python 3.11+. Detached mode waits for the health check and exits
nonzero on failure. Alternatively run `docker compose up --build --detach --wait`
directly. First-time setup can take longer than the wrapper's 30-minute wait on
slow connections; inspect `docker compose logs setup` and rerun after it finishes.

Use Ctrl+C to stop a foreground run. For a detached run:

```sh
docker compose logs -f
docker compose down
```

Stopping preserves `models/` and `var/docker/`. The running application mounts
models read-only. To change the port without the wrapper, set `CHEMLAB_PORT`
(for example, `$env:CHEMLAB_PORT='8081'` in PowerShell or
`CHEMLAB_PORT=8081 docker compose up --build` in a POSIX shell).

## Start without Docker

Install 64-bit Python **3.11** with `venv`/`ensurepip` available, then run:

```sh
python start_venv.py
```

On Windows, `py -3.11 start_venv.py` selects the right interpreter. On Linux or
macOS, use `python3.11 start_venv.py` if `python` names another version. The
launcher creates `.venv`, installs the pinned dependencies there, downloads and
registers the same models/data, and serves [ChemLab](http://127.0.0.1:8080).
Activation and global package installation are unnecessary. Run the same command
again to reuse the environment and downloads. Ctrl+C stops the server.

```sh
python start_venv.py --port 8081
python start_venv.py --venv .venv-other --state var/other --prepare-only
```

Python 3.11 on Linux is the tested native runtime. Windows interpreter selection
has contract tests; a native Windows/macOS end-to-end run has not been performed.
Newer Python versions require all pinned packages to publish compatible wheels.
The macOS launcher uses Torch 2.14.1 without the Linux/Windows `+cpu` build suffix;
this is a different platform build, not a cross-platform bit-identity promise.

Minimal Debian/Ubuntu installs may first need OS packages installed by their
administrator: `python3.11-venv`, `libxrender1`, `libxext6`, `libgomp1`, `libexpat1`,
`libfreetype6` and `fonts-dejavu-core`. Other systems need the equivalent native
libraries used by RDKit/Pillow/PyTorch. A failed dependency install exits before
starting the application. An incomplete existing venv is preserved; choose a new
`--venv` path to recover. Do not run two servers against the same state directory.

## First-run data and persistence

Allow several GB of disk space and an internet connection for dependency wheels,
two checkpoint archives and their extracted weights (about 1.7 GB), stock and the
public precedent corpus. A CPU is sufficient; inference can take minutes.
Models load on the first search. Subsequent launches reuse complete downloaded
files and verify registered artifact identities; they do not replace checkpoints.
Interrupted/inconsistent artifacts fail setup and need inspection.

| Path | Purpose |
| --- | --- |
| `models/` | Shared checkpoint downloads, tokenizer files and public source data |
| `.venv/` | Native Python dependencies |
| `var/local/` | Native registry, cache, runs and evidence bundles |
| `var/docker/` | Container registry, cache, runs and evidence bundles |

Models and the frozen runtime ZIP are versioned through Git LFS. The venv and
mutable state directories remain ignored by Git. Native and container registries
are separate because model manifests bind absolute checkpoint paths. Keep the state directory with its
corresponding environment. Use one launcher at a time while it prepares shared
model downloads. Both launch paths bind the web interface to localhost only.

The downloader uses official Figshare archives and checks the publisher's archive
checksum and size. Registration hashes the checkpoint directory and tokenizer.
The default stock is the PaRoutes v2 n1 snapshot: benchmark stock, not a live
supplier catalog.

Setup imports the 40,008-record OpenRetro USPTO-50K training split for exact
represented-reaction precedent lookup. Its Git blob and original source bytes
are verified and retained. Unsupported source rows are quarantined with an audit.
This corpus is not independent confirmation; overlap with a future benchmark must
be audited. The underlying dataset license is not separately specified in the
inspected repository, and is recorded separately from its MIT code license.

## Restore the included runtime history (optional, Docker)

The frozen ZIP contains the SQLite registry/cache and complete evidence bundles
for seven prior runs. It is a consistent database backup with per-file hashes;
WAL/shared-memory files and unfinished runs are excluded. It preserves the
original `/workspace/var` and `/workspace/models` bindings, so use it with Docker.
The native launcher prepares its own platform-specific registry instead.

On a fresh clone, before starting the application:

```sh
docker compose build setup
docker compose --profile artifacts run --rm restore
docker compose up --build
```

Restore validates the archive's paths, sizes, hashes, database and complete
bundles, then publishes to `var/docker`. It requires that directory to be absent
and refuses to overwrite any existing state. If you already ran the app, keep
using your current state; the downloaded snapshot stays available for inspection.
Stopping the app and deleting existing data is not part of this restore command.

The snapshot is historical computational evidence, not a new chemical validation
or a portable cache for arbitrary model versions/platforms. New runtime activity
remains local; it does not modify the committed download.

## CLI

Run CLI commands in the configured environment:

```sh
docker compose run --rm --no-deps chemlab list
.venv/Scripts/python.exe -m chemlab --store var/local list
.venv/bin/python -m chemlab --store var/local list
```

The native examples select Windows and POSIX interpreters respectively. Run
commands from the checkout and use the matching state directory.

- `list`: inspect registered models, stocks and corpora.
- `register-model ALIAS manifest.json`: register a new immutable model version.
- `import-stock ALIAS stock.txt --source SOURCE --license TERMS`: import SMILES.
- `import-corpus ALIAS corpus.json`: import partitioned reaction precedent.
- `run 'TARGET_SMILES' --config configs/local.json`: search and verify.
- `show RUN_ID`: inspect a completed or failed run.
- `check-bundle PATH`: validate publication hashes and references.
- `reverify RUN_ID`: reconstruct stored routes and compare replayed reports.
- `parity MODEL INPUT... --count K`: compare direct provider and adapter outputs.
- `dataset-audit reactions.jsonl`: audit target and reaction overlap by partition.
- `dataset-export reactions.jsonl OUTPUT`: export training/development data only.

`configs/local.json` is a development run configuration. It is not a frozen
scientific benchmark. Change it deliberately before freezing a final experiment.
Its route threshold counts distinct candidate route identities before verification.

## Custom generators

Generation is a replaceable single-step provider; the search engine builds the
route. A provider can use its own tokenizer, graph representation and neural
architecture internally. It must emit the common product/precursor contract and
declare score semantics. The checker is selected independently.

See `docs/provider-contract.md`. The project does not expose a training command
for a model architecture that has not been designed or trained. Dataset export,
partition auditing, provider registration and parity checks are available now.

## Validation

```powershell
docker build --target test -t chemlab:test .
docker run --rm --network none --read-only --tmpfs /tmp chemlab:test -q --basetemp=/tmp/tests -o cache_dir=/tmp/pytest-cache
docker run --rm --network none --read-only --tmpfs /tmp --entrypoint python chemlab:test scripts/mutation_checks.py
```

Contract tests include positive routes and seeded corruptions. The bounded graph
experiment exhaustively compares 1,572 cases with a separately formulated graph
oracle. Mutation experiments require assertion failures rather than import/setup
errors. These are scoped software checks, not proof of chemical feasibility.

The current acceptance suite passes 111 tests and detects 16 named mutations;
lint, formatting and type checks also pass. The current distribution suite is
under `evaluation/reports/lfs-distribution/`. Earlier startup evidence is under
`evaluation/reports/startup-acceptance/`, with the built-image suite under
`evaluation/reports/startup-image-acceptance/`. A fresh isolated Linux venv
completed real pretrained route generation and verification. Compose passed
automatic initialization, restart, health/registry/rendering checks and a failed
setup injection that kept the app stopped. These startup checks reused the
existing model/data downloads; they do not establish native Windows/macOS support
or chemical accuracy.

## Boundaries and sources

- RDKit: molecular identity and representations.
- RDChiral: recorded template application/replay.
- Syntheseus: pinned Retro* search; project-owned adapters and independent export checks.
- Pydantic: versioned records and validation.
- SQLite: registry, cache references and run state.
- FastAPI: local API shared with the CLI's application service.

No upstream source has been copied into this repository. Necessary integration
behavior is isolated in adapters, with contract fixtures.

Pretrained checkpoints: standalone RetroChimeraDeNovo and ForwardChimeraDeNovo,
MIT licenses on their official Figshare records:
https://figshare.com/articles/software/RetroChimeraDeNovo_Pistachio_/31150195
https://figshare.com/articles/software/ForwardChimeraDeNovo_Pistachio_/32994914

Both use Pistachio training data. Their agreement is not independent confirmation.
Training overlap with a future evaluation dataset must be audited/disclosed.

The current specification is `ARCHITECTURE.md`, together with the unchanged
identity, status and verification contracts in the original architecture document.
Research experiments and limitations are recorded in `RESEARCH.md`.
