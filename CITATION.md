# Citing ChemLab

If you use ChemLab in research, cite the software and record the exact Git commit
used. The version below is the package version; a commit identifies the specific
implementation and accompanying evidence.

```bibtex
@software{chemlab2026,
  author = {{soumik15630m}},
  title = {ChemLab: Evidence-bound retrosynthesis planning and independent route verification},
  year = {2026},
  version = {0.1.0},
  url = {https://github.com/soumik15630m/chemlab}
}
```

Repository: [soumik15630m/chemlab](https://github.com/soumik15630m/chemlab).
No archival DOI has been assigned in this citation.

## Reproducing a result

Alongside the software citation, report the commit, dependency versions, model
checkpoint and tokenizer hashes, stock and corpus snapshots, identity policy,
search and verification settings, seeds and execution environment. Retain the
exported evidence bundle and its hashes. Distinguish artifact replay from fresh
neural inference, and structural verification from experimental feasibility.

## Upstream software, models and data

Cite the upstream projects and artifacts actually used in your experiment in
addition to ChemLab. The default integration uses:

- [Syntheseus](https://github.com/microsoft/syntheseus) for Retro* search.
- [RDKit](https://www.rdkit.org/) for molecular representations and identity.
- [RDChiral](https://github.com/connorcoley/rdchiral) for template application.
- [RetroChimeraDeNovo (Pistachio)](https://figshare.com/articles/software/RetroChimeraDeNovo_Pistachio_/31150195)
  and [ForwardChimeraDeNovo (Pistachio)](https://figshare.com/articles/software/ForwardChimeraDeNovo_Pistachio_/32994914)
  for reaction proposals and forward evidence.
- [PaRoutes v2](https://zenodo.org/records/7341155) for the n1 stock snapshot.
- [OpenRetro](https://github.com/coleygroup/openretro) for the USPTO-50K training
  split used in represented-reaction precedent lookup.

Use each upstream project's recommended citation for the pinned version you
used. See [artifact sources](docs/artifact-sources.md) for exact source records,
license boundaries and data limitations. The project's Apache-2.0 license does
not replace upstream software, checkpoint or dataset terms.
