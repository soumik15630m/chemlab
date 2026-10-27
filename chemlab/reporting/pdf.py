"""Human-readable report of existing evidence, without changing its conclusions."""

from __future__ import annotations

import io
from functools import partial
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from chemlab.chemistry import require_molecule
from chemlab.reporting.formats import molecule_image, reaction_image, selected_route

LIMITATION = (
    "Structural verification and forward agreement do not prove experimental feasibility. "
    "Public precedent is reported evidence, not independent confirmation. "
    "Reaction conditions and experimental procedures are outside V1."
)


def molecule_pdf(smiles: str) -> bytes:
    identity = require_molecule(smiles)
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    mono = ParagraphStyle(
        "MoleculeSMILES", fontName="Courier", fontSize=8, leading=12, splitLongWords=True
    )
    story = [
        Paragraph("ChemLab / Molecular structure", styles["Title"]),
        Image(io.BytesIO(molecule_image(identity.canonical_smiles)), width=480, height=144),
        Paragraph(escape(identity.canonical_smiles), mono),
        Spacer(1, 18),
        Paragraph(
            "Identity policy: identity-v1. Stereo, isotopes, charge and fragments are retained.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        Paragraph(
            "Deterministic 2D depiction; not an optimized 3D geometry. "
            "This structure download does not claim a reaction or experimental feasibility.",
            styles["BodyText"],
        ),
    ]
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        title="ChemLab molecular structure",
        author="ChemLab",
        invariant=1,
    )
    document.build(story, canvasmaker=partial(Canvas, invariant=1))
    return output.getvalue()


def report_pdf(bundle: dict[str, Any]) -> bytes:
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    ink = colors.HexColor("#18302c")
    green = colors.HexColor("#206b54")
    styles.add(
        ParagraphStyle(
            "ChemTitle",
            fontName="Times-Roman",
            fontSize=29,
            leading=34,
            textColor=ink,
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            "ChemHeading",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=18,
            textColor=green,
            spaceBefore=14,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "ChemBody",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            spaceAfter=8,
            splitLongWords=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "ChemMono",
            fontName="Courier",
            fontSize=7,
            leading=10,
            spaceAfter=8,
            splitLongWords=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "ChemSmall",
            fontName="Helvetica",
            fontSize=7,
            leading=10,
            spaceAfter=5,
            splitLongWords=True,
        )
    )

    def para(text: Any, style: str = "ChemBody"):
        value = str(text).encode("ascii", "backslashreplace").decode("ascii")
        return Paragraph(escape(value), styles[style])

    def frame(canvas, document):
        canvas.setStrokeColor(colors.HexColor("#d9dfd5"))
        canvas.line(48, 802, 547, 802)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(green)
        canvas.drawString(48, 813, "CHEMLAB  /  SYNTHESIS EVIDENCE")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(ink)
        canvas.drawString(48, 28, "Research output | 2D depictions | No experimental guarantee")
        canvas.drawRightString(547, 28, f"Page {document.page}")

    run = bundle["objects"][bundle["run_ref"]]["payload"]
    story: list[Any] = [
        para("Synthesis route report", "ChemTitle"),
        para("Target molecule", "ChemHeading"),
        para(run["target"], "ChemMono"),
        Image(io.BytesIO(molecule_image(run["target"])), width=480, height=144),
        para(LIMITATION),
        para(f"Run ID: {bundle['run_id']}", "ChemSmall"),
        para(f"Completed: {run.get('completed_at', 'not recorded')}", "ChemSmall"),
        para("Search outcome", "ChemHeading"),
    ]
    group_labels = {
        "verified_consistent": "Structurally verified / forward consistent",
        "verified_other_evidence": "Structurally verified / other forward evidence",
        "availability": "Already in stock",
        "unresolved": "Unresolved routes",
        "rejected": "Rejected diagnostics",
    }
    for group, items in bundle["groups"].items():
        story.append(para(f"{group_labels.get(group, group)}: {len(items)}"))
    if run.get("experimental"):
        story.append(
            para("Computational fixture: test data, not model-generated chemical evidence.")
        )
    search = run["search"]
    story.extend(
        [
            para(
                f"Logical expansions: {search['logical_expansions']} | "
                f"Model calls: {search['actual_inferences']} | Cache hits: {search['cache_hits']}"
            ),
            para(
                f"Search stopped: {search['termination_reason']}. "
                "Budget exhaustion is not chemical unsynthesizability."
            ),
            para("Bound inputs and provenance", "ChemHeading"),
        ]
    )
    for key in (
        "config_ref",
        "backward_manifest_ref",
        "forward_manifest_ref",
        "stock_ref",
        "corpus_ref",
    ):
        story.append(para(f"{key}: {run.get(key)}", "ChemMono"))
    number = 0
    for items in bundle["groups"].values():
        for item in items:
            report_data = bundle["objects"][item["report_ref"]]["payload"]
            if report_data["structural_status"] != "verified":
                continue
            route, report = selected_route(bundle, item["route_ref"])
            number += 1
            story.extend(
                [
                    PageBreak(),
                    para(f"Route {number}", "ChemTitle"),
                    para(
                        f"Structural: {report.structural_status} | "
                        f"Forward: {report.forward_status}",
                        "ChemHeading",
                    ),
                    para(f"Verification policy: {report.policy} | Molecular identity: identity-v1"),
                    para(f"Route reference: {item['route_ref']}", "ChemMono"),
                ]
            )
            if not route.steps:
                story.append(
                    para(
                        "Target already occurs in the pinned stock. No synthesis steps are claimed."
                    )
                )
            for step in route.steps:
                story.append(
                    para(f"Transformation {step.id} / precursors to product", "ChemHeading")
                )
                story.append(Image(io.BytesIO(reaction_image(route, step)), width=492, height=130))
                molecules = {m.id: m.molecule.canonical_smiles for m in route.molecules}
                story.append(
                    para(
                        "Reactants: " + " + ".join(molecules[mid] for mid in step.precursor_ids),
                        "ChemMono",
                    )
                )
                story.append(para("Product: " + molecules[step.product_id], "ChemMono"))
                precedent = report.precedent.get(step.id, {})
                if isinstance(precedent, dict):
                    lookup = precedent.get("status", "not recorded")
                    if lookup == "pass":
                        lookup = "completed"
                    story.append(
                        para(
                            f"Precedent lookup: {lookup} | "
                            f"Match: {precedent.get('match_type', 'not recorded')}",
                            "ChemSmall",
                        )
                    )
                    for source_id, reference in precedent.get("references", {}).items():
                        story.append(para(f"Source {source_id}: {reference}", "ChemSmall"))
            story.append(para("Recorded checks", "ChemHeading"))
            rows = [
                [
                    para("Check", "ChemSmall"),
                    para("Status", "ChemSmall"),
                    para("Reason", "ChemSmall"),
                ]
            ]
            for check in report.checks:
                rows.append(
                    [
                        para(check.name, "ChemSmall"),
                        para(check.status.replace("_", " "), "ChemSmall"),
                        para(check.reason, "ChemSmall"),
                    ]
                )
            table = LongTable(rows, colWidths=[145, 90, 257], repeatRows=1, splitInRow=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eee5")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d9dfd5")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.extend([table, Spacer(1, 14), para(LIMITATION, "ChemSmall")])
    if number == 0:
        story.append(
            para(
                "No structurally verified routes were published for this search. "
                "See the evidence bundle for rejected and unresolved diagnostics."
            )
        )
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=54,
        bottomMargin=48,
        title="ChemLab synthesis route report",
        author="ChemLab",
        invariant=1,
    )
    document.build(
        story, onFirstPage=frame, onLaterPages=frame, canvasmaker=partial(Canvas, invariant=1)
    )
    return output.getvalue()
