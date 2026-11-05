"""Build the public technical report PDF from its maintained HTML source."""
from pathlib import Path
import subprocess
import sys
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(ROOT / "scripts/build_report_figures.py")], check=True)
report = ROOT / "app/static/report"
destination = report / "sonvane-technical-report.pdf"
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto((report / "index.html").as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.pdf(
        path=str(destination), format="A4", prefer_css_page_size=True,
        print_background=True, display_header_footer=True,
        header_template="<span></span>",
        footer_template=(
            '<div style="font:8px Arial;color:#536579;width:100%;margin:0 60px;'
            'display:flex;justify-content:space-between">'
            '<span>Sonvane · Technical report · 4 November 2026</span>'
            '<span><span class="pageNumber"></span> / '
            '<span class="totalPages"></span></span></div>'
        ),
    )
    browser.close()
print(destination)
