# Molecule, reaction and report downloads

The target preview and molecule cards offer a PDF structure sheet and a MOL file.
Completed searches offer a PDF evidence report. Every structurally verified route
offers an editable chemistry ZIP; unresolved/rejected routes remain available in
the original complete evidence bundle and in the PDF's diagnostic counts.

| Download | Contents and use |
| --- | --- |
| PDF | Target depiction, route reaction schemes, separate evidence statuses, checks and source references |
| MOL V3000 | Individual molecular occurrence with a deterministic 2D depiction |
| SDF V3000 | All route occurrences with IDs, canonical SMILES, route reference and evidence-status properties |
| RXN V3000 | One represented reaction per step, precursors on the left and product on the right |
| SMILES | Molecular occurrences and reaction SMILES, including grouped disconnected participants |
| SVG | Vector reaction schemes for figures and presentations |
| JSON | Exact stored route/report records and export manifest with per-file SHA-256 hashes |

The editable ZIP preserves occurrences and precursor multiplicity rather than
deduplicating equal structures. Its manifest connects molecule files to occurrence
IDs and reaction files to product/precursor occurrence IDs. Mapping, conditions,
stoichiometry, by-products and 3D conformers are not invented. Reaction schemes
describe represented transformations; they are not experimental procedures.

Every MOL, SDF, RXN and reaction-SMILES export is reimported with the pinned RDKit.
Full identity-v1 identities and participant multiplicities must match before the
download is returned. Stereo, isotopes, charge and disconnected fragments are
retained. A format-conversion failure is an error, never a partially successful
chemistry download. Route/report binding and structural status are checked before
an editable route package is generated.

PDFs repeat the original structural/forward statuses and verification policy.
They distinguish a completed precedent lookup from an actual source match, retain
conflicting evidence and disclose synthetic fixture runs. Generated PDF metadata
uses a fixed timestamp for repeatable bytes in the pinned runtime; the real run's
completion time is printed in the report. Fixed ZIP timestamps likewise avoid
changing an export solely because it was downloaded again.

## Chemistry software interoperability

These are exchange files, not native CDX/CDXML/MRV projects. The choice follows
the vendors' documented file-format support:

- [ChemDraw product format matrix](https://revvitysignals.com/sites/default/files/2025-06/Full%20Dot%20Chart%20ChemDraw%20Suite%20of%20Products.pdf)
  lists MOL, SDF and RXN with V2000/V3000 support.
- [Chemaxon MDL format documentation](https://docs.chemaxon.com/lts-silicon/formats_mdl-molfiles-rgfiles-sdfiles-rxnfiles-rdfiles-formats.html)
  covers molecule, structure-data and reaction formats.
- [RDKit molecule serialization](https://rdkit.org/docs/source/rdkit.Chem.rdmolfiles.html)
  and [reaction serialization](https://rdkit.org/docs/source/rdkit.Chem.rdChemReactions.html)
  define the pinned exporter/reimporter boundary.

Compatibility is supported by vendor documentation and tested by RDKit reimport.
ChemDraw/Marvin themselves have not been executed here. Application edition,
version and import options can affect presentation; a 2D depiction is not a
computed 3D geometry. Editing an exported file does not retain its verification
status automatically.
