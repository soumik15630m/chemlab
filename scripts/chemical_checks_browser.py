"""Exercise the live reaction-check UI, model worker, history and downloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--saved-run")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        registry = page.request.get(args.url + "/api/registry").json()
        knowledge = [r for r in registry if r["kind"] == "reaction_knowledge"]
        previous_jobs = page.request.get(args.url + "/api/chemical-jobs").json()
        expect(page.locator("#knowledge option")).to_have_count(len(knowledge) + 1)
        preferred = next((r for r in knowledge if r["alias"] == "lowe-context-v2"), None)
        if preferred:
            expect(page.locator("#knowledge")).to_have_value(preferred["ref"])
        page.locator("#reaction-smiles").fill("CCO>>CC=O")
        page.locator("#reaction-form button").click()
        report = page.locator("#reaction-result")
        expect(report).to_contain_text("Chemical evidence / complete", timeout=180000)
        expect(report.locator(".badge.support, .badge.unresolved")).to_have_count(1)
        expect(report).to_contain_text("mapped_product_atoms_have_provenance")
        expect(report).to_contain_text("Experimental feasibility remains unresolved")
        page.locator("#reaction-result").scroll_into_view_if_needed()
        page.screenshot(path=str(args.output / "reaction-check-desktop.png"), full_page=True)
        downloads = []
        for label, suffix in (
            ("Evidence JSON", ".json"),
            ("Evidence PDF", ".pdf"),
            ("Editable reaction files", ".zip"),
        ):
            with page.expect_download() as pending:
                report.get_by_role("link", name=label, exact=True).click()
            download = pending.value
            assert download.suggested_filename.endswith(suffix)
            download.save_as(args.output / ("reaction-evidence" + suffix))
            downloads.append(download.suggested_filename)
        page.reload()
        expect(page.locator("#chemical-history button")).to_have_count(len(previous_jobs) + 1)
        current_jobs = page.request.get(args.url + "/api/chemical-jobs").json()
        assert {row["id"] for row in previous_jobs} < {row["id"] for row in current_jobs}
        page.locator("#chemical-history button").first.click()
        expect(report).to_contain_text("Chemical evidence / complete")
        page.locator("#reaction-smiles").fill("C>>CN")
        page.locator("#reaction-form button").click()
        expect(report.locator(".badge.contradiction")).to_have_count(1, timeout=180000)
        expect(report).to_contain_text("listed_atom_source_missing")
        page.set_viewport_size({"width": 390, "height": 844})
        report.scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(args.output / "reaction-check-mobile.png"), full_page=True)
        if args.saved_run:
            page.set_viewport_size({"width": 1440, "height": 1100})
            rows = page.request.get(args.url + "/api/runs").json()
            index = next(i for i, row in enumerate(rows) if row["id"] == args.saved_run)
            page.locator("#runs .run-link").nth(index).click()
            section = page.locator("#result > section.route").first
            section.get_by_role(
                "button", name="Check every reaction in this route", exact=True
            ).click()
            expect(section).to_contain_text("Chemical evidence / complete", timeout=180000)
            expect(section).to_contain_text("Every step is required")
            expect(section).to_contain_text("Experimental feasibility remains unresolved")
            for label, suffix in (
                ("Evidence JSON", ".json"),
                ("Evidence PDF", ".pdf"),
                ("Editable reaction files", ".zip"),
            ):
                with page.expect_download() as pending:
                    section.get_by_role("link", name=label, exact=True).click()
                pending.value.save_as(args.output / ("saved-route-evidence" + suffix))
            section.scroll_into_view_if_needed()
            page.screenshot(path=str(args.output / "saved-route-check.png"), full_page=True)
        assert not errors, errors
        browser.close()
    (args.output / "result.json").write_text(
        json.dumps(
            {
                "passed": True,
                "javascript_errors": errors,
                "downloads": downloads,
                "saved_run": args.saved_run,
                "scope": (
                    "Live UI and pinned offline mapping worker; not chemical feasibility accuracy"
                ),
            },
            indent=2,
        ),
        encoding="ascii",
    )


if __name__ == "__main__":
    main()
