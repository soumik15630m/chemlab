# Reaction challenge observations, 28 October 2026

Scope: development observations and software validation. No automatic chemical
classifier, experimental replication or final evaluation result is claimed.

Authoritative final software validation: `final-validation-2/validation.json` and
`final-validation-2/mutation-report.json`. Lint, formatting and mypy pass; 145 tests
pass with zero failures/errors/skips; all 25 named Python mutants are detected.
`validation/` preserves the earlier 144-test/24-mutant run. `final-validation/`
preserves an intervening lint failure in a newly added mutation declaration,
corrected before final validation. No failed chemistry experiment is represented
as a software formatting failure or vice versa.

- `observations.json`: 14 routes and 39 step occurrences, with original input
  hashes and separate user route labels (3 correct, 9 incorrect, 2 unlabelled).
- `packaged-replay.json`: all 14 diagnostic results match the portable challenge
  snapshot when read from the original complete bundles and original PDF hashes.
  The source bundles were mounted read-only; no new inference was requested.
- `runtime-provenance.json`: final packaged source matches 65 working-tree files,
  all 84 pinned dependency versions match and `pip check` passes. The image is
  `sha256:5f7ab00152af10d6bf685c01f97e899290edd6dc9f3e092296567b9201717fe6`.
  It was packaged offline over the existing pinned dependency image, not built
  through a new network dependency installation.
- `browser/`: Chromium frontend contract checks with controlled API responses;
  desktop/mobile layout, visible unresolved chemistry, five distinct route
  numbers, failed-request retry and JSON attachment bytes pass. No JavaScript
  errors or horizontal mobile overflow were detected. Structure pictures are
  explicitly controlled fixtures; this is not live chemical drawing validation.
- `browser-scope-mutant/` and `browser-number-mutant/`: false feasibility wording
  and repeated route numbers cause assertion failures without JavaScript errors.
  These two browser mutants are separate from the 25 Python mutants.
- `local-app.json`: the updated Compose app is healthy, all 11 saved runs remain,
  four live observation endpoints match replay and all three original PDF
  downloads remain byte-identical. No fresh model inference was requested.

Material negative result: inventory observations find no missing elements among
the listed inputs. All 39 steps lack supplied mapping, so mapping-dependent bond
edits are unknown. These diagnostics do not identify the nine incorrect-labelled
routes as chemically wrong. Two incorrect-labelled routes agree with the forward
model; one correct-labelled route conflicts with it. These selected cases do not
estimate population accuracy. Every chemical assessment remains unresolved.

See `docs/reaction-verification-development.md` for the 22-transformation manual
analysis, source distinctions, execution commands and next research obligations.
`docs/chemical-knowledge-layer.md` describes the next research design; it is not an
implemented acceptance policy. Models, stock, identity, frozen forward decisions,
mapping profiles, baseline search and existing bundles were not changed.
