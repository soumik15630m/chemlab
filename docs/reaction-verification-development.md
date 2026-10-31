# Reaction verification development

## Scope and current result

The 28 October 2026 development work adds read-only observations and a reproducible
challenge set. It does not establish a chemical validity oracle or change engine
acceptance, identity-v1, mapping profiles, model checkpoints, search or frozen
forward decisions. No reaction family has been promoted to automatic chemical
acceptance or rejection.

The user labelled pyranopyrazole routes 1, 3 and 5 correct, all five isoindoline
routes incorrect, and all four fused-spirooxindole routes incorrect. Pyranopyrazole
routes 2 and 4 remain unlabelled. These are complete-route labels, not step-level
experimental ground truth. The earlier manual audit's plausible-route judgments
are hypotheses, not a replacement for these labels.

The cases retain 64 original hash-bound objects, 14 routes, 39 step occurrences
and 22 distinct represented transformations. Two incorrect-labelled routes have
forward agreement; one correct-labelled route has forward conflict. These are
selected counterexamples, not estimates of model precision or sensitivity.

## Step-level failure analysis

References S1-S5 are the primary sources recorded in
[the manual audit](../evaluation/reports/manual-reaction-audit-2026-10-27.md).
Literature support for an individual step does not validate a whole route. Where
the specific failure cannot be established, it remains unresolved rather than
being invented from the complete-route label. The challenge JSON supplies exact
SMILES, candidate indices, source references and recorded forward outcomes for
every occurrence below.

| Case | Occurrences in PDF order | Observation and remaining chemical question |
| --- | --- | --- |
| A1 | 470792 R1 s0 | Ethyl acetoacetate/hydrazine to methylpyrazolone; supported reaction family S1/S2. Isolation/tautomer and conditions remain outside the recorded proposal. |
| A2 | 470792 R1/R4 s1 | Pyrazolone/benzaldehyde/malononitrile ring formation; S1 supports the phenyl product family. R1 is user-labelled correct. |
| A3 | 470792 R2 s0 | Methyl acetoacetate/hydrazine to hydroxy tautomer. Not independently labelled; do not infer exact isolated form from a related preparation. |
| A4 | 470792 R2 s1 | Hydroxy-tautomer ring formation; related to A2, with a different exact starting identity. Route remains unlabelled. |
| A5 | 470792 R3 s0 | Alternate NH/OH representation of the preformed pyrazolone plus aldehyde/malononitrile. User-labelled correct route; representation remains explicit. |
| A6 | 470792 R4 s0 | Methyl ester to keto pyrazolone. Forward top-five ranks 2/5 share an enumerated tautomer with the expected product, but exact identity still fails. Route remains unlabelled. |
| A7 | 470792 R5 s0 | Four-component synthesis supported by S1/S2 and user-labelled correct; frozen forward top five misses the target. This is a model counterexample, not a reason to change the label. |
| B1 | 7b270a R1/R2 s0 | Phthalimide to isoindolinone is documented in S3. A route-level incorrect label does not establish this step as wrong. |
| B2 | 7b270a R1 s1 | Oxonium-mediated lactim ether preparation supported by S4. This does not establish the later target-forming sequence. |
| B3 | 7b270a R2 s1 | Diethyl sulfate variant: exact substrate/product selectivity not established by the S4 oxonium example. |
| B4 | 7b270a R1/R2 s2; R5 s1 | Cyanoacetate/imidate coupling: exact connectivity and drawn alkene stereochemistry lack an independently established example in this audit. |
| B5 | 7b270a R1-R4 s3; R5 s2 | Ester aminolysis: exact substrate outcome and retained stereochemistry unresolved. Do not call it wrong merely because the whole route is wrong. |
| B6 | 7b270a R3 s0 | Orthoacetate/TFAA to orthocarbonate: unsupported change of central-carbon substitution. Listed atoms alone neither explain this transformation nor prove it impossible. |
| B7 | 7b270a R4 s0 | Orthoacetate/triphosgene variant: same unsupported orthocarbonate preparation question. |
| B8 | 7b270a R3/R4 s1 | Orthocarbonate/cyanoacetate to ketene acetal: specific transformation unvalidated; cannot repair the preceding unsupported step. |
| B9 | 7b270a R3/R4 s2 | Bromobenzylamine annulation requires specific aryl C-C bond formation and ring closure. Generic condensation evidence does not establish it. |
| B10 | 7b270a R5 s0 | Orthoformate/benzylamine to fused cyclic imidate requires unsupported new aryl-carbon connectivity. Exact supporting transformation not located. |
| C1 | c403c0 R1/R3 s0 | Isatin/cyanoacetate/cyanoacetamide to the particular diamino spiro-pyran: exact connectivity and atom provenance unresolved. |
| C2 | c403c0 R2/R4 s0 | Malononitrile alternative to the same intermediate: distinct inputs require separate support; not validated by C1 analogy. |
| C3 | c403c0 R1/R2 s1 | Diamine/cyanogen bromide to 2-aminobenzimidazole is supported by S5. This step does not validate the route. |
| C4 | c403c0 R3/R4 s1 | Advanced substituted benzimidazole to the small amine requires several unexplained substituent cleavages. By-products may carry lost atoms; atom loss alone is not an impossibility proof. |
| C5 | c403c0 R1-R4 s2 | Final fused-ring annulation: exact precursor pair/product connectivity unvalidated. All four complete routes are user-labelled incorrect. |

## Executable observations

`chemlab/evidence/reaction_diagnostics.py` provides three scoped observations:

- Heavy-atom inventories preserve precursor occurrences, fragments and isotope
  labels. They flag elements or isotope labels without a listed source. Counts
  are representation counts, not stoichiometry. Missing reagents can explain
  missing sources; isotope labels are not claims about natural isotope abundance.
- Bond-edit observations require an applicable supplied mapping, product atom
  provenance and complete heavy-atom map coverage. They list bond appearances,
  absences, order changes, lost main-product atoms and formal-charge changes.
  They do not establish a mechanism. Invalid/missing mappings supply no edits.
- Bounded tautomer enumeration compares saved forward representations. It records
  original ranks, exact matches, diagnostic overlap and unknown results. Specified
  stereo and isotopic inputs are excluded from non-exact tautomer comparisons.
  Incomplete enumeration is unknown. No salt stripping, neutralization, identity
  merging or new inference occurs.

The actual challenge run found no elements missing from listed precursors. All
39 steps lack supplied mappings, so every mapping-dependent edit observation is
unknown. These observations therefore do not automatically identify the nine
incorrect-labelled routes. This negative result is material: atom inventories
alone cannot resolve the failures motivating the project.

The saved comparisons contain 22 exact matches, 9 shared-tautomer observations,
102 different enumerated forms and 62 unknown comparisons (58 outside the stereo/
isotope scope and 4 incomplete enumerations). Repeated steps are counted as
occurrences, not independent evidence. Every route's chemical assessment remains
unresolved; correct-labelled routes retain their structural and evidence results.

The app exposes observations on demand and as a JSON attachment. Each result binds
its route/report, candidate indices and original prediction references and records
the diagnostic/RDKit versions. Failures remain visible. Existing PDF reports keep
their original structural/forward distinction and experimental limitation; they
do not incorporate this new sidecar as previously recorded evidence.

Reproduce in the project's Docker environment:

```sh
python scripts/reaction_challenges.py --output /tmp/challenge-observations.json
python -m pytest tests/test_reaction_diagnostics.py -q
```

The report writer refuses to overwrite an existing output. The committed result
and validation evidence are under
`evaluation/reports/reaction-challenges-2026-10-28/`.

## Promotion path

Further exact-fragment/name searches found related isoindoline and spiro-isatin
literature, but no new primary example establishing the unresolved transformations.
In particular, the primary
[Beilstein study of aminoarylimidazoles](https://www.beilstein-journals.org/bjoc/articles/15/101)
reports a different aminoazole scaffold and pyrroloimidazole products. It cannot
validate the proposed benzimidazole/fused-pyran annulation merely because isatin
and active-methylene partners occur in both. Likewise, an extra ring carbonyl
changes an isoindolinylidene structure; similarly named compounds cannot share
exact precedent automatically. A constructed positive/negative retrieval fixture
and a seeded product-identity defect exercise that boundary. This does not
establish a chemical failure for either target.

Before any chemical acceptance profile is proposed, establish step-level reference
judgments, including the failing stereochemical or connectivity claim where known.
Collect independently reviewed positive and negative cases with exact structures,
primary source locations, limitations and uncertainty. Hold evaluation examples
apart before developing thresholds or reaction-specific checks. Source similarity,
an exact represented corpus hit and agreement between Pistachio-trained models
must remain distinguishable from independent experimental support.

New diagnostics first run as observations and must detect relevant seeded defects
without penalizing supported alternatives. Unknown/error paths need equal care.
Only demonstrated, explicitly scoped behavior can be proposed as a mandatory
check. Adding a new acceptance policy, mapping requirement or search pruning is a
separate contract decision; none is introduced by this work.

RDKit API boundaries follow the
[tautomer-enumeration API](https://www.rdkit.org/docs/source/rdkit.Chem.MolStandardize.rdMolStandardize.html)
and [representation documentation](https://www.rdkit.org/docs/RDKit_Book.html),
with contract tests against the actual pinned runtime rather than assuming that
documentation establishes chemical correctness.
