"""Exercise the real frontend with controlled read-only API responses in Chromium."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    snapshot = json.loads((root / "tests/fixtures/reaction-challenges/snapshot.json").read_bytes())
    bundle = {**snapshot["reports"][0]["completion"], "objects": snapshot["objects"]}
    run = bundle["objects"][bundle["run_ref"]]["payload"]
    row = {"id": bundle["run_id"], "target": run["target"], "state": "complete", "result": bundle}
    observations = {
        "mode": "read_only_observations",
        "chemical_assessment": "unresolved",
        "limitation": "Controlled frontend fixture; no chemical validity established.",
        "steps": [
            {"step_id": "s0", "mapped_edits": {"status": "unknown", "reason": "mapping_missing"}}
        ],
    }
    result: dict = {
        "passed": False,
        "javascript_errors": [],
        "api_requests": [],
        "scope": "Frontend contract with controlled API responses; not live inference",
    }
    failed_once = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
            page.on("pageerror", lambda error: result["javascript_errors"].append(str(error)))

            def respond(route):
                nonlocal failed_once
                path = urlsplit(route.request.url).path
                if path.startswith("/api/"):
                    result["api_requests"].append({"method": route.request.method, "path": path})
                if path == "/":
                    route.fulfill(path=root / "chemlab/web/index.html", content_type="text/html")
                elif path.startswith("/static/"):
                    filename = path.rsplit("/", 1)[1]
                    mime = "text/javascript" if filename.endswith(".js") else "text/css"
                    route.fulfill(path=root / "chemlab/web" / filename, content_type=mime)
                elif path == "/api/registry":
                    route.fulfill(json=[])
                elif path == "/api/chemical-jobs":
                    route.fulfill(json=[])
                elif path == "/api/runs":
                    route.fulfill(json=[{k: row[k] for k in ("id", "target", "state")}])
                elif path == f"/api/runs/{row['id']}":
                    route.fulfill(json=row)
                elif path.endswith("/observations.json"):
                    if not failed_once:
                        failed_once = True
                        route.fulfill(
                            status=409, json={"detail": "Observation evidence unavailable"}
                        )
                    else:
                        route.fulfill(
                            json=observations,
                            headers={
                                "Content-Disposition": 'attachment; filename="observations.json"',
                            },
                        )
                elif path == "/api/molecule.svg":
                    route.fulfill(
                        content_type="image/svg+xml",
                        body=(
                            '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60">'
                            '<text x="10" y="30">Structure fixture</text></svg>'
                        ),
                    )
                else:
                    route.fulfill(status=404, body="Unconfigured frontend fixture endpoint")

            page.route("**/*", respond)
            page.goto("http://127.0.0.1:8080/", wait_until="networkidle")
            page.locator("#runs button").first.click()
            sections = page.locator("section.route")
            expect(sections).to_have_count(5)
            for number in range(1, 6):
                section = sections.nth(number - 1)
                expect(section.locator("h3")).to_contain_text(f"Route {number} /")
                expect(section).to_contain_text("Chemical feasibility: unresolved.")
            section = sections.first
            section.get_by_text("Inspect reaction observations", exact=True).click()
            section.get_by_role("button", name="Load observations").click()
            expect(section).to_contain_text("Observation evidence unavailable")
            expect(section.get_by_role("button", name="Load observations")).to_be_enabled()
            section.get_by_role("button", name="Load observations").click()
            expect(section).to_contain_text('"mode": "read_only_observations"')
            expect(section).to_contain_text('"reason": "mapping_missing"')
            with page.expect_download(timeout=5000) as download:
                section.get_by_role("link", name="Reaction observations (JSON)").click()
            assert json.loads(Path(download.value.path()).read_bytes()) == observations
            page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
            assert not result["javascript_errors"]
            assert all(r["method"] == "GET" for r in result["api_requests"])
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
