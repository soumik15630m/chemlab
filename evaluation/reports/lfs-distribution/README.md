# Distribution evidence

`release-distribution.json` records all 12 objects acknowledged by the standard
Git LFS client, local object/pointer integrity checks and a fresh clone from
GitHub. Eight downloaded files were independently checked by size and SHA-256.
The four largest files were not independently redownloaded in that clone.

The final missing checkpoint was uploaded by the explicitly approved disposable
Docker job in `hosted-transfer.json`. It checked the original Figshare archive
and extracted checkpoint against their pinned hashes before using Git LFS.
`transfer-workflow-state.json` records that the one-off workflow was disabled
after success. Its isolated branch remains available for audit.

Local upload attempts encountered repeated DNS failures. The fallback container
transfer was intentionally stopped only after GitHub confirmed the checkpoint
was present. These are operational distribution checks, not chemical evidence.
