# Dependency adaptations

No upstream source files are copied or edited. The following integration behavior
is isolated in project-owned adapters and must pass contract tests against the
pinned versions. Changes here are not automatically safe because upstream is
widely used.

## Syntheseus 0.9.0 - deterministic occurrence-tree integration

Observed in the installed implementation: graph expansion iterates over
`reaction.unique_reactants`, a set. Message propagation returns collections
that can have nondeterministic iteration order. Route extraction sums costs over
node sets. These details can affect ties or floating-point accumulation order.

Adaptation:

- `DeterministicReaction` preserves set semantics but orders reactant
  iteration by complete canonical identity.
- `BudgetedRetroStar` orders visited/updated nodes by their full ancestor path,
  molecule identity and reaction dependency signature before queue insertion.
- Route extraction receives exact rational representations of finite float costs.
  Its set sums therefore do not depend on addition order. Exported costs retain
  the declared baseline score representation.
- Unique planner nodes are disabled; ancestor-cycle prevention is enabled.
- Logical expansion accounting wraps the public model call, including cache hits.
- Route export reconstructs distinct occurrences and binds every step to its
  original adapter record. The verifier checks it independently.

Validation: search contract fixtures, repeated-intermediate tests, bounded graph
tests and fresh-process tests with different Python hash seeds. Validation status
and reports are recorded in `RESEARCH.md`; this adaptation is not an unbounded
proof of the upstream implementation.

## RDKit 2026.9.1 / RDChiral 1.1.0

Identity-v1 explicitly removes map numbers only for identity keys and preserves
isotopes, charge, fragments and specified stereo. Inputs outside the admitted
representation are rejected with reasons. RDChiral replay is bound to recorded
vocabulary and application settings; enantiomer-combining is disabled.

The packaged RDKit type stubs contain an upstream signature syntax error. Mypy
does not follow those external stubs; runtime chemistry contracts are tested
explicitly. Project source remains type-checked. No chemistry check is bypassed.
