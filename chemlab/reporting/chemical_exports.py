"""Portable reaction-evidence reports and identity-preserving input structures."""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections import Counter
from functools import partial
from xml.sax.saxutils import escape

from rdkit import Chem
from rdkit.Chem import rdChemReactions
from rdkit.Chem.Draw import rdMolDraw2D
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from chemlab.evidence.reaction_library import reaction_input
from chemlab.records import canonical_bytes, digest
from chemlab.reporting.formats import (
    depiction_molecule,
    molecule_identity,
    molecule_mol,
    reaction_participants,
)
from chemlab.store import IntegrityError

LIMITATION = (
    "Experimental feasibility remains unresolved. Support means reported precedent or a "
    "source-derived structural analogy. Contradiction concerns listed atom sources; omitted "
    "reagents can change that finding. Conditions, yields and procedures are excluded."
)


def report_reactions(job: dict) -> list[tuple[str, dict]]:
    if job["state"] != "complete":
        raise ValueError("Chemical evidence is not completely published")
    result = job["result"]
    for key, reaction in result["results"].items():
        query = reaction_input(reaction["input"]["product"], tuple(reaction["input"]["precursors"]))
        if digest(query) != key or reaction["input_key"] != key:
            raise IntegrityError("Chemical export reaction binding mismatch")
        if reaction["policy_hash"] != result["policy_hash"]:
            raise IntegrityError("Chemical export policy binding mismatch")
    binding = result["route_binding"]
    if binding:
        if {s["input_key"] for s in binding["steps"]} != set(result["results"]):
            raise IntegrityError("Route evidence does not cover every distinct selected step")
        return [(s["step_id"], result["results"][s["input_key"]]) for s in binding["steps"]]
    return [(f"Reaction {n}", reaction) for n, reaction in enumerate(result["results"].values(), 1)]


def represented_reaction(query: dict):
    reaction = rdChemReactions.ChemicalReaction()
    for smiles in query["precursors"]:
        reaction.AddReactantTemplate(depiction_molecule(smiles))
    reaction.AddProductTemplate(depiction_molecule(query["product"]))
    return reaction


def evidence_pdf(job: dict) -> bytes:
    reactions = report_reactions(job)
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 12
    styles.add(
        ParagraphStyle(
            "EvidenceMono",
            fontName="Courier",
            fontSize=7,
            leading=10,
            splitLongWords=True,
            spaceAfter=8,
        )
    )
    body = styles["BodyText"]
    story = [
        Paragraph("ChemLab / Reaction evidence", styles["Title"]),
        Paragraph(LIMITATION, body),
        Spacer(1, 14),
        Paragraph("Report binding", styles["Heading2"]),
        Paragraph(escape(job["result_ref"]), styles["EvidenceMono"]),
        Paragraph("Policy: " + escape(job["result"]["policy_hash"]), styles["EvidenceMono"]),
        Paragraph(
            "Knowledge: "
            + escape(job["result"].get("knowledge_name", "See bound knowledge record")),
            body,
        ),
    ]
    if job["result"]["route_binding"]:
        story.extend(
            [
                Paragraph(
                    "Route: " + escape(job["result"]["route_binding"]["route_ref"]),
                    styles["EvidenceMono"],
                ),
                Paragraph("Every selected reaction occurrence appears below.", body),
            ]
        )
    summary = job["result"].get("route_summary")
    if summary:
        story.append(
            Paragraph(
                escape(
                    f"Required step occurrences: {summary['step_occurrences']}. "
                    f"Route evidence: {summary['evidence_outcome']}. {summary['limitation']}"
                ),
                body,
            )
        )
    for number, (label, assessment) in enumerate(reactions, 1):
        if number > 1:
            story.append(PageBreak())
        query = assessment["input"]
        story.extend(
            [
                Spacer(1, 12),
                Paragraph(escape(label), styles["Heading1"]),
                Paragraph(
                    "Evidence outcome: " + escape(assessment["evidence_outcome"]),
                    styles["Heading2"],
                ),
            ]
        )
        drawer = rdMolDraw2D.MolDraw2DCairo(1440, 380)
        drawer.DrawReaction(represented_reaction(query))
        drawer.FinishDrawing()
        story.append(Image(io.BytesIO(drawer.GetDrawingText()), width=480, height=127))
        story.append(
            Paragraph(
                escape(".".join(query["precursors"]) + ">>" + query["product"]),
                styles["EvidenceMono"],
            )
        )
        rows = [[Paragraph("Check", body), Paragraph("Outcome / scope", body)]]
        for name, check in assessment["checks"].items():
            detail = check.get("reason") or check.get("interpretation") or "See evidence JSON"
            rows.append(
                [
                    Paragraph(escape(name.replace("_", " ")), body),
                    Paragraph(
                        escape((str(check["status"]) + " / " + detail).replace("_", " ")), body
                    ),
                ]
            )
        table = LongTable(rows, colWidths=[140, 340], repeatRows=1, hAlign="LEFT")
        table.setStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eee7")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#477062")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
        story.append(table)
        inventory = assessment["checks"]["atom_origin"]
        missing = inventory.get("elements_without_listed_source", [])
        isotopes = inventory.get("isotope_labels_without_listed_source", [])
        if missing or isotopes:
            story.append(
                Paragraph(
                    escape(f"Unaccounted listed sources: {missing}; isotope labels: {isotopes}"),
                    body,
                )
            )
        for name in ("exact_precedent", "context_precedent"):
            evidence = assessment["checks"][name]
            matches = evidence.get("matches", [])
            if not matches:
                continue
            heading = Paragraph(escape(name.replace("_", " ")), styles["Heading3"])
            story.append(
                KeepTogether(
                    [
                        heading,
                        Paragraph(
                            f"{len(matches)} returned source records; "
                            "duplicated reports are not independent confirmations.",
                            body,
                        ),
                    ]
                )
            )
            for match in matches[:10]:
                story.append(Paragraph(escape(f"{match['source']} / row {match['row']}"), body))
                story.append(Paragraph(escape(match["reference"]), styles["EvidenceMono"]))
            if len(matches) > 10:
                story.append(
                    Paragraph(
                        "Additional returned sources are retained in the evidence JSON.", body
                    )
                )
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        title="ChemLab reaction evidence",
        author="ChemLab",
        invariant=1,
    )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#61736e"))
        canvas.drawString(48, 30, "Experimental feasibility unresolved. Conditions excluded.")
        canvas.drawRightString(A4[0] - 48, 30, f"Page {document.page}")
        canvas.restoreState()

    document.build(
        story, onFirstPage=footer, onLaterPages=footer, canvasmaker=partial(Canvas, invariant=1)
    )
    return output.getvalue()


def evidence_chemistry_zip(job: dict) -> bytes:
    reactions = report_reactions(job)
    files = {"chemical-report.json": canonical_bytes(job)}
    sdf = io.StringIO()
    writer = Chem.SDWriter(sdf)
    writer.SetForceV3000(True)
    reaction_lines = []
    expected_molecules = []
    for number, (label, assessment) in enumerate(reactions, 1):
        query = assessment["input"]
        reaction = represented_reaction(query)
        expected = (Counter(query["precursors"]), Counter({query["product"]: 1}))
        if reaction_participants(reaction) != expected:
            raise IntegrityError("Chemical evidence depiction changed represented participants")
        block = rdChemReactions.ReactionToV3KRxnBlock(reaction)
        restored = rdChemReactions.ReactionFromRxnBlock(block, sanitize=True, removeHs=False)
        if reaction_participants(restored) != expected:
            raise IntegrityError("Chemical evidence RXN changed input identities")
        smiles = rdChemReactions.ReactionToSmiles(reaction, canonical=True)
        if (
            reaction_participants(rdChemReactions.ReactionFromSmarts(smiles, useSmiles=True))
            != expected
        ):
            raise IntegrityError("Chemical evidence SMILES changed input identities")
        files[f"reactions/reaction-{number:04d}.rxn"] = block.encode("ascii")
        reaction_lines.append(smiles)
        for occurrence, identity in enumerate([*query["precursors"], query["product"]], 1):
            expected_molecules.append(identity)
            molblock = molecule_mol(identity)
            name = f"molecules/reaction-{number:04d}-molecule-{occurrence:04d}.mol"
            files[name] = molblock
            mol = Chem.MolFromMolBlock(molblock.decode("ascii"), sanitize=True, removeHs=False)
            mol.SetProp("_Name", f"{label} / molecule {occurrence}")
            mol.SetProp(
                "role", "product" if occurrence == len(query["precursors"]) + 1 else "precursor"
            )
            mol.SetProp("evidence_outcome", assessment["evidence_outcome"])
            writer.write(mol)
    writer.close()
    files["molecules.sdf"] = sdf.getvalue().encode("ascii")
    restored_molecules = list(
        Chem.ForwardSDMolSupplier(
            io.BytesIO(files["molecules.sdf"]),
            sanitize=True,
            removeHs=False,
        )
    )
    if [molecule_identity(mol) for mol in restored_molecules] != expected_molecules:
        raise IntegrityError("Chemical evidence SDF changed input identities or occurrences")
    files["reactions.smi"] = ("\n".join(reaction_lines) + "\n").encode("ascii")
    files["manifest.json"] = canonical_bytes(
        {
            "identity": "identity-v1",
            "report_ref": job["result_ref"],
            "limitation": LIMITATION,
            "files": {
                name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())
            },
        }
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output.getvalue()
