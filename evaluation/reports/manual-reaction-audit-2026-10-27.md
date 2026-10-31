# Manual literature audit of three user-selected ChemLab reports

Reviewed 27 October 2026. Scope: the exact structures and transformations in the
three supplied PDFs, their saved prediction evidence, and accessible primary
literature/patents. This is a manual chemical assessment, not an experimental
replication, a frozen benchmark, or a new engine acceptance policy. Absence of a
located precedent is not proof that a transformation is impossible.

The reports contain 14 candidate routes and 39 displayed step occurrences.
Repeated steps and tautomeric representations are not independent confirmations.
No inference was rerun and no stored report, identity policy or model was changed.

## 470792e991c24516ac93beda4c2fd67a: pyranopyrazole

Target: `Cc1n[nH]c2c1C(c1ccccc1)C(C#N)=C(N)O2`.

Verdict: substantial, genuine literature support for the core synthesis.

| PDF route | Assessment |
| --- | --- |
| 1 | Ethyl acetoacetate/hydrazine to methylpyrazolone, then condensation with benzaldehyde and malononitrile: credible established chemistry [S1, S2]. |
| 2 | Methyl acetoacetate/hydrazine variant followed by the same ring formation: chemically credible; exact intermediate tautomer is a representation issue rather than a separately validated isolated product. |
| 3 | Preformed hydroxypyrazole/pyrazolone plus benzaldehyde and malononitrile: credible reaction family [S1]; the starting NH/OH representation must remain explicit. |
| 4 | The methyl-ester route is chemically credible despite the recorded forward conflict. Its first-step top-five evidence contains the hydroxy tautomers but not the selected keto representation. |
| 5 | Direct four-component reaction: the strongest explicit counterexample to treating forward conflict as invalid chemistry. The same reagent combination and target scaffold are documented [S1, S2]. |

S1 reports the phenyl product 4a with characterization and formula C14H12N4O.
This supports the transformation; it does not establish a yield or preferred
tautomer for ChemLab's condition-free proposals.

Saved evidence for route 4, step s0:
`1e139dc101095986628f2000b83a374d6c76fdd9a3303fb84093e24c4426909a`.
Expected product: `CC1=NNC(=O)C1`.
Forward outputs include `Cc1cc(O)[nH]n1` (rank 2) and
`Cc1cc(O)n[nH]1` (rank 5). An independent RDKit tautomer-family check in the
pinned container maps all three to `Cc1cc(=O)[nH][nH]1`. This diagnostic check
does not alter identity-v1 or turn the stored exact-match failure into a pass.

Saved evidence for route 5, step s0:
`CCOC(=O)CC(C)=O.N#CCC#N.NN.O=Cc1ccccc1`.
The target is absent from the frozen top five, even though S1/S2 support the
four-component synthesis. The model's disagreement is therefore not a sound
reason to discard this reaction family.

## 7b270a4b59074c3781e5b2cd44a1d8d3: isoindolinylidene cyanoacetamide

Target: `N#C/C(C(N)=O)=C1/NCc2ccccc21`.

Verdict: route 1 is a reasonable lead, not a fully literature-verified route to
the exact Z product. Route 2 has weaker support. Routes 3-5 are not defensible
as supplied.

| Step or route | Assessment |
| --- | --- |
| Routes 1/2 s0: phthalimide to isoindolinone | Exact substrate/product pair is genuinely described in the report's cited patent, Example 66 [S3]. Reagents/conditions are omitted by V1, not evidence that the substrate reduces itself. |
| Route 1 s1: triethyloxonium plus isoindolinone to lactim ether | Direct support for phthalimidine conversion to its imino ether in the experimental section of Fang/Gerig [S4]. The counterion/workup are absent from the PDF. |
| Route 2 s1: diethyl sulfate alternative | O-ethylation is chemically conceivable, but exact selectivity and this substrate/product pair were not independently established here. Do not equate its model score with S4's evidence. |
| Shared cyanoacetate condensation | A plausible activated-imidate/carbon-nucleophile transformation. No exact experimental example establishing the drawn product and Z selectivity was located in this audit. |
| Shared ester plus ammonia to amide | Plausible ester aminolysis. Exact substrate conversion, competing reactions and retained Z geometry remain unverified. |
| Routes 3/4 s0: triethyl orthoacetate plus TFAA/triphosgene to tetraethyl orthocarbonate | Major unsupported structural edit: a methyl-bearing orthoester becomes an orthocarbonate. No matching experimental support found. This is not ordinary exchange of ethoxy groups. Strong suspected model hallucination; not a claim of universal impossibility. |
| Routes 3/4 s1: orthocarbonate/cyanoacetate to ketene acetal | Chemically conceivable in isolation, but it does not rescue the unsupported preceding preparation. Exact example not established. |
| Routes 3/4 s2: bromobenzylamine annulation | Needs specific evidence for C-C formation/aryl-bromide cyclization and product geometry. No exact support located; a generic amine condensation does not establish this ring closure. |
| Route 5 s0: benzylamine/triethyl orthoformate to cyclic imidate | Unsupported as supplied: introduces a fused ring through new aryl-carbon bonding. Ordinary orthoformate/amine condensation alone is not proof of this transformation. |

Missing conditions alone do not make a V1 proposal wrong. The issue is the lack
of independent support for several specific bond changes and stereochemical
claims, even where the forward model agrees.

## c403c0ac85714302a10bc322929da630: fused spirooxindole

Target: `N#CC1=C(N)Oc2nc3[nH]c4ccccc4n3c(=O)c2C12C(=O)Nc1ccccc12`.

Verdict: no complete route independently validated; do not use these four
proposals as established synthesis routes.

| Step or route | Assessment |
| --- | --- |
| Routes 1/2 s1: o-phenylenediamine/cyanogen bromide to 2-aminobenzimidazole | Genuine documented chemistry [S5]. This one good step does not validate the rest of either route. |
| Routes 1/3 s0: isatin, ethyl cyanoacetate, cyanoacetamide to the drawn diamino spiro-pyran | No exact supporting example found. The highly specific intermediate and regiochemistry require evidence; a related spiro-pyran paper is insufficient. |
| Routes 2/4 s0: malononitrile variant to the same intermediate | Likewise unvalidated; substrate substitution changes mechanistic and atom-provenance questions. |
| All routes, final annulation with 2-aminobenzimidazole | No exact precedent found for the displayed precursor pair and fused product connectivity. Must remain unvalidated. |
| Routes 3/4 s1: advanced C21H26FN5 substrate to C7H7N3 | Strong red flag: multiple substituent cleavages with no supporting transformation evidence. Loss of atoms into by-products is not itself a conservation violation, but this is an unjustified proposed preparation. |

All four PDF routes already have forward conflict. Routes 3/4 conflict at every
step; routes 1/2 conflict at s0 and s2. Structural verification here checks the
route record, graph, stock and provenance. It does not certify these bond
changes as chemically feasible.

## Implications for the engine

The audit provides a named representation-mismatch case (4707 route 4 s0), a
literature-supported forward-model miss (4707 route 5), and several unvalidated
alternative-route cases. These are case studies, not precision/recall estimates.
No final evaluation dataset, cache key, top-k, identity definition or baseline
pruning rule should change silently in response.

The intended chemical correctness requirement is not met by a green structural
badge plus model agreement alone. Keep exact structural/provenance checks, but
make their scope unmistakable. Any stronger chemical acceptance layer requires
independent evidence and explicit unresolved outcomes, not reinterpretation of
the existing check statuses.

## Primary sources checked

- S1: Al-Matar et al., Molecules 2010, 15, 6619-6629, product 4a and synthesis section.
  https://doi.org/10.3390/molecules15096619
  Open full-text record: https://pmc.ncbi.nlm.nih.gov/articles/PMC6257727/
- S2: Bihani, Bora and Bez, Journal of Chemistry 2013, article 920719.
  https://onlinelibrary.wiley.com/doi/10.1155/2013/920719
  This paper also reports difficulty reproducing some earlier reaction conditions;
  literature support for a transformation does not guarantee every published procedure.
- S3: US20070010455A1, Example 66, phthalimide to 2,3-dihydroisoindol-1-one.
  https://patents.google.com/patent/US20070010455A1/en
- S4: Fang and Gerig, Nuclear magnetic resonance studies of several N-acylisoindolines,
  JACS 1969, 91, 3045-3049, experimental preparation of the imino ether.
  https://doi.org/10.1021/ja01039a037
  Primary-paper scan inspected through indexed experimental text:
  https://electronicsandbooks.com/edt/manual/Magazine/J/Journal%20of%20the%20American%20Chemical%20Society%20US/1969%20%20%28vol%20091%29/11%20%20%282823-3110%29/3045-3049.pdf
- S5: Noolvi et al., Synthesis, antimicrobial and cytotoxic activity of novel
  azetidine-2-one derivatives of 1H-benzimidazole, section 2.1.1.
  https://doi.org/10.1016/j.arabjc.2011.02.011
  https://arabjchem.org/synthesis-antimicrobial-and-cytotoxic-activity-of-novel-azetidine-2-one-derivatives-of-1h-benzimidazole/

Some publisher/full-text pages were intermittently inaccessible to the web tool.
The exact patent experimental passage and S4 experimental preparation were
available in indexed primary-document text; full S2/S5 text was accessible.
Unrelated catalog entries, generic reviews and similarly named structures were
not accepted as exact reaction validation. Searches included exact structure
fragments/names and reagent combinations; they are not an exhaustive literature search.
