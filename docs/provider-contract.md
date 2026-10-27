# Provider contract

A generator returns single-step precursor proposals. Syntheseus builds routes;
the verifier reconstructs them independently. A provider cannot mark a route
verified, override identity-v1 or supply an acceptance flag.

## Manifest

Register a versioned `ModelManifest` through the local CLI. Its schema is exposed
by `chemlab.records.ModelManifest.model_json_schema()`. Fields bind:

- Provider name, kind, backend, architecture and representation.
- Checkpoint path and SHA-256 content hash; directory hashes bind every file name
  and file content. Use `chemlab.adapters.sdk.content_hash` in the container.
- Optional tokenizer path/hash and provider version.
- Supported inputs and preprocessing. Backward baseline preprocessing preserves
  identity; information-losing conversion is rejected at startup.
- Score semantics/direction, decoding, backend, dtype, determinism and seed.
- Ordered template vocabulary and application settings for template-based output.
- Training provenance and separate code/checkpoint license information.

Choose a new alias when changing weights, vocabulary, settings or code version.
Aliases cannot silently point at a different immutable manifest.

## Python provider

Use `backend: "python"` and `model_class: "package.module:ClassName"`.
The class constructor accepts the validated manifest. It loads its runtime once.
Its `predict(effective_input: str, num_results: int)` method returns a list of
JSON-compatible records:

```json
[
  {
    "precursors": ["CCO", "CC(=O)O"],
    "score": 1.0,
    "template_id": "ester-cleavage"
  }
]
```

This example describes a deterministic template cost of one, not a feasibility
probability. Preserve every original precursor occurrence, including duplicates.
For disconnected salts/fragments that form one precursor record, preserve the
original record boundary instead of splitting it to create artificial reactants.
Optional mapping uses `mapped_reaction`, with precursor side first and product
side second. Declare `mapping_required` if a mandatory operation consumes it.

The built-in `chemlab.adapters.sdk:TemplateLibraryProvider` is a complete
deterministic provider. It applies the declared RDChiral vocabulary in recorded
order, uses sorted outcomes and a unit step cost. It is also an integration
example for custom models; it is not a trained reaction predictor.

## Native Syntheseus provider

Use `backend: "syntheseus"` with an importable class path. The adapter calls the
provider's public interface and disables its optional outer deduplication. The
native implementation may have internal decoding/reranking; preserve its
public output and metadata, and declare those settings. The stored raw output
is the provider-boundary response, not a claim to contain every internal logit.

Template-based native implementations must expose template provenance. An
implementation that drops template IDs cannot meet the mandatory replay contract
through a generic wrapper; use a dedicated provider or an isolated upstream patch.

## Command provider

Use `backend: "command"` and an explicit argv list. The adapter invokes it without
a shell, sends one JSON request on stdin and reads one JSON response from stdout.
The request includes `input`, `num_results` and the full manifest. Response:

```json
{
  "effective_input": "CCOC(C)=O",
  "predictions": [{"precursors": ["CCO", "CC(=O)O"], "score": 0.8}]
}
```

Return the exact effective input to bind the response. Log diagnostics to stderr.
Timeouts, process failures and invalid JSON become error artifacts, never empty
successful predictions. A command process is isolated per request; use a Python
provider or a command client to a separately managed persistent runtime when model
load cost matters. Pin that runtime and record its settings as well.

## Forward checker

The same provider interface accepts the combined precursor representation and
returns `{"product": "PRODUCT_SMILES"}` records. Its manifest kind is `forward`.
The engine stores the requested list and applies its own exact identity/stereo
comparison. A model cannot return a boolean chemical-validity decision in place
of the product list. Conditions are outside v1.

## Admission

Run direct/adapter parity on a fixed reference set. Include invalid outputs,
duplicate precursors, stereo, score ties and checkpoint/vocabulary mismatches.
Demonstrate that relevant tests catch seeded defects. Do not allow errors or
unknowns to become passes. A new tokenizer/architecture remains experimental until
it passes the same boundary tests and a separate evaluation of prediction quality.
