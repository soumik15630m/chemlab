from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


def main(output: Path) -> int:
    process = subprocess.Popen(
        [sys.executable, "-m", "chemlab", "serve", "--port", "8080"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            try:
                with urlopen("http://127.0.0.1:8080/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:8080", wait_until="networkidle")
            page.get_by_role("heading", name="Plan a synthesis").wait_for()
            assert page.locator("#generator option").count() >= 1
            assert page.locator("#checker option").count() >= 1
            assert page.locator("#stock option").count() >= 1
            assert not page.locator("#submit").is_disabled()
            page.locator(".run-link").first.click()
            page.get_by_text("Download complete evidence bundle").wait_for()
            page.locator(".molecule-card").first.wait_for()
            page.screenshot(path=str(output / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(output / "mobile.png"), full_page=True)
            browser.close()
        report = {
            "passed": not errors,
            "javascript_errors": errors,
            "checks": [
                "registered model selectors",
                "completed real-model route display",
                "molecule rendering",
                "desktop layout",
                "mobile overflow",
            ],
            "scope": "Chromium browser smoke test; not an accessibility or chemical benchmark",
        }
        (output / "browser-smoke.json").write_text(json.dumps(report, indent=2), encoding="ascii")
        print(json.dumps(report))
        return 0 if report["passed"] else 1
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
