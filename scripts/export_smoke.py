"""Render one real published run and validate its chemistry exchange package."""

import argparse
import io
import json
import zipfile
from pathlib import Path

from pypdf import PdfReader

from chemlab.reporting.bundles import read_bundle
from chemlab.reporting.formats import chemistry_zip
from chemlab.reporting.pdf import report_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    bundle = read_bundle(args.bundle)
    data = report_pdf(bundle)
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "do not prove experimental feasibility" in text
    assert "US20050148627A1:train-row-15" in text
    assert data == report_pdf(bundle)
    item = bundle["groups"]["verified_consistent"][0]
    chemistry = chemistry_zip(bundle, item["route_ref"])
    with zipfile.ZipFile(io.BytesIO(chemistry)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["steps"]) == 2
        assert "molecules.sdf" in archive.namelist()
        assert "reactions/step-0001.rxn" in archive.namelist()
    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    args.pdf.write_bytes(data)
    args.pdf.with_suffix(".chemistry.zip").write_bytes(chemistry)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "passed": True,
        "run_id": bundle["run_id"],
        "pages": len(reader.pages),
        "pdf_deterministic": True,
        "chemistry_files": sorted(manifest["files"]),
        "scope": (
            "RDKit reimport and real saved evidence; "
            "no vendor application or chemical feasibility claim"
        ),
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
