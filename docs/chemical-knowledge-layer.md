# Chemical knowledge layer

The executable evidence layer now implements immutable patent-reaction lookup,
validated auxiliary mapping, source-derived RDChiral context retrieval and exact
precursor replay. See [reaction checking](reaction-checking.md) for operation and
the distinction between evidence and chemical acceptance. The broader obligations
below remain a research design wherever they lack a validated implementation;
they are not exposed as working feasibility rules.

## Objective

Given represented reactants and a proposed product, explain what supports the
transformation, what contradicts it under a stated context, and which necessary
questions remain unanswered. A route needs an assessment for every selected
step. A model score or an atom map cannot answer those questions on its own.

The implementation should reuse the existing immutable store, source ingestion,
identity-v1 matching, partition audit and check statuses. It must not create a
parallel planner or train a generator to compensate for absent verification.

## Knowledge and provenance

Represent source documents separately from extracted reaction claims. A source
record needs its original location, exact content hash and retained bytes where
redistribution permits. A claim needs the precise source location, explicitly
represented participants, product identity, experimental context and observation
type. Recorded success, reported failure under particular conditions, proposed
mechanism and model suggestion are different kinds of information.

Record how a claim was transcribed and reviewed. A content hash identifies bytes;
it does not establish that a paper says what an extractor claims. Similar names,
an extra carbonyl, unspecified stereo, different counterions and tautomeric
representations cannot silently become exact evidence. Family-level analogies
remain family-level evidence. Complete-route user judgments cannot manufacture
negative step-level examples.

Track source lineage and dataset membership so repeated patents, derivatives of
the same dataset and models sharing training data do not become independent
confirmations. Final-reference material must remain outside guidance and evidence
retrieval. Claims need immutable versions; corrections retain their history.

## Reaction obligations

Use the proposed bond changes to pose questions, rather than assigning a
feasibility probability. Examples include the source of a newly introduced atom,
which bond closes a ring, which center determines stereochemistry, and whether a
proposed transformation requires an activation step or a protecting-group change.
Each obligation needs a declared domain and evidence requirements. A rule may be
tested only where its prerequisites are known to apply.

Supplied or inferred mappings first need identity/provenance checks. Ambiguous
atom correspondence remains ambiguous, especially in symmetric molecules.
Mapping-dependent obligations cannot be discharged when mapping is unavailable
or invalid. Observation of a bond change does not establish its mechanism.

Reaction-family constraints should begin with narrow, independently supported
substrate domains and include competing outcomes and valid exceptions. Missing
conditions in V1 frequently prevent discharging a contextual obligation. They do
not establish that no conditions could make a transformation work.

## Energetic and learned evidence

Any later energetic calculation must bind the actual species, charge, spin,
tautomer/conformer choices, environment, method and convergence record. Failure
to converge is not chemical rejection. A product energy is not an activation
barrier, and a favorable energy difference does not establish selectivity or an
accessible pathway. Existing xTB artifacts may be reused only when their inputs
and provenance qualify.

Additional learned feasibility or mapping components remain replaceable evidence
providers. Their applicability and shared training provenance need explicit
evaluation. No ensemble agreement can substitute for a missing deterministic
check or an absent experimental claim.

## Validation before authority

Develop against step-level cases with independently established expected results.
Include plausible-looking errors, supported multicomponent reactions, genuine
alternative preparations, stereo counterexamples and explicit unknown/error
cases. A rule that rejects every reaction fails its positive controls.

Separate development cases from an untouched evaluation set before selecting
rules or thresholds. Report denominators by domain, errors, abstentions and
evidence coverage. Keep historical labels and disagreements visible. Challenge
examples selected after model failures cannot estimate general accuracy.

Run each proposed validator as an observation first. Demonstrate relevant mutant
detection and characterize false rejection before proposing an acceptance role.
The deliverable for promotion is a concrete scope, supported cases, counterexamples,
failure behavior and reproducible evidence. A new mandatory profile or search
pruning rule requires an explicit contract decision. Until that evidence exists,
the engine must expose unresolved chemistry instead of claiming certainty.
