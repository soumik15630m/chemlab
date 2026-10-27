"""Exercise download controls through Chromium, including actual attachment bytes."""

import argparse
import json
import re
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--molecule-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {
        "passed": False,
        "javascript_errors": [],
        "mode": "molecule" if args.molecule_only else "full",
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
            page.on("pageerror", lambda error: result["javascript_errors"].append(str(error)))
            page.goto(args.url, wait_until="networkidle")
            page.locator("#target").fill("[13CH3][C@H](O)F")
            page.locator("#target").dispatch_event("change")
            with page.expect_download(timeout=5000) as download:
                page.locator("#preview").get_by_role("link", name="Molecule PDF").click()
            assert Path(download.value.path()).read_bytes().startswith(b"%PDF-")
            with page.expect_download(timeout=5000) as download:
                page.locator("#preview").get_by_role("link", name="MOL file").click()
            assert b"V3000" in Path(download.value.path()).read_bytes()
            if not args.molecule_only:
                page.get_by_role("button", name=re.compile(r"^Oc1ccc.*complete")).first.click()
                with page.expect_download(timeout=10000) as download:
                    page.get_by_role("link", name="Download PDF report").click()
                assert Path(download.value.path()).read_bytes().startswith(b"%PDF-")
                with page.expect_download(timeout=10000) as download:
                    page.get_by_role(
                        "link", name="Editable chemistry files", exact=False
                    ).first.click()
                with zipfile.ZipFile(download.value.path()) as archive:
                    assert "molecules.sdf" in archive.namelist()
                    assert any(name.endswith(".rxn") for name in archive.namelist())
                page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
            assert not result["javascript_errors"]
            browser.close()
        result["passed"] = True
        return 0
    except Exception as exc:
        result["failure_kind"] = type(exc).__name__
        result["error"] = str(exc)
        return 1
    finally:
        (args.output / "browser.json").write_text(json.dumps(result, indent=2), encoding="ascii")
        print(json.dumps(result))


if __name__ == "__main__":
    raise SystemExit(main())
