# User-labelled reaction challenges

Development cases from three user-selected reports, labelled on 28 October 2026.
These are not final evaluation data and must not enter runtime guidance, precedent
retrieval or model training as independently established chemical ground truth.

- `labels.json`: manually transcribed complete-route verdicts. Correct: 470792
  routes 1, 3, 5. Incorrect: every route in 7b270a and c403c0. Other routes remain
  unlabelled. No step labels or experimental outcomes were supplied.
- `snapshot.json`: selected original content-addressed route, report, generator
  prediction and forward-evidence envelopes (64 objects). The source completion
  manifests and original PDF hashes are retained. Source bytes hash to
  `771cd13845e7f8324144b14d615875ae102ebcf4e9a14fffd9c27b75b0fde602`.

The snapshot excludes stock/corpus/model payloads and is deliberately not a full
replay bundle. It does not independently attest the original adapter registry.
The original complete bundles remain the replay/provenance authority. Checks
here preserve selected hashes and bindings; they do not recreate experimental
evidence from hashes. The user PDFs are not needed to execute these tests.

Route numbers refer to PDF order, with structurally verified/forward-consistent
routes followed by structurally verified/other-evidence routes. Full route hashes
and PDF hashes disambiguate each label. Tests check the preserved snapshot hash,
label totals, both directions of forward-model disagreement and positive cases.

The observations are independent of the labels. Changing a user label does not
change computed inventories, mapping observations or representation comparisons.
