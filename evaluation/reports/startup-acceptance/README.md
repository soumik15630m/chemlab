# Startup acceptance scope

- `validation.json`: working-tree lint, format, typing, 101 contract tests and
  14 seeded mutations. Source and launcher/configuration hashes are recorded.
- `native-startup.json`: fresh isolated Python 3.11 venv inside a disposable Linux
  container, pinned CPU dependencies, automatic model/data registration, HTTP
  readiness, molecule rendering and a real pretrained search with two
  structurally verified, forward-consistent routes.
- `compose-startup.json`: Compose builds and initializes the shared image,
  registers four artifacts, imports 40,008 public records and serves the API/SVG.
- `compose-failure.json`: setup was made to exit 17. Compose returned nonzero and
  the application remained created, without ever starting.
- `runtime.json`: image identity and state of the final local Compose application.

The native venv did not inherit system site packages. Model/data downloads were
reused in both startup checks. Compose was checked with a fresh registry, then
restarted using that registry and an initially absent shared image tag. Test
containers were disposed of; model/data and the existing application state were
preserved. Native Windows and macOS have not been exercised end to end.

The final built image also passes the full suite without a working-tree mount;
see `../startup-image-acceptance/validation.json`. These are computational and
operational checks, not proof of experimental reaction feasibility.
