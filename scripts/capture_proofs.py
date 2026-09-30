"""Script to capture visual proofs of the ForestSentinel map, reports, and charts."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import markdown_it
from PIL import Image

def main():
    base_dir = Path(".").resolve()
    proofs_dir = base_dir / "reports" / "proofs"
    proofs_dir.mkdir(parents=True, exist_ok=True)

    charts_dir = base_dir / "reports" / "charts" / "20260930_102826"
    map_html = charts_dir / "fire_activity_map.html"
    report_md = base_dir / "reports" / "analysis_report_20260930_102836.md"

    print("=== Capturing ForestSentinel Verification Proofs ===")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 960})

        # 1. Capture Interactive Folium Map
        if map_html.exists():
            print(f"Loading map: {map_html.name}")
            page.goto(map_html.as_uri())
            page.wait_for_timeout(3500)  # Wait for tiles and markers to render
            map_png = proofs_dir / "proof_01_folium_map.png"
            page.screenshot(path=str(map_png), full_page=False)
            print(f"  [+] Saved Folium Map proof: {map_png.name} ({map_png.stat().st_size:,} bytes)")

        # 2. Render Markdown report to HTML and capture full page screenshot
        if report_md.exists():
            print(f"Loading report: {report_md.name}")
            md_content = report_md.read_text(encoding="utf-8")
            md = markdown_it.MarkdownIt()
            html_body = md.render(md_content)

            styled_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ForestSentinel Analysis Report Proof</title>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #1E2A22;
    background: #F6F5EF;
    max-width: 980px;
    margin: 40px auto;
    padding: 30px;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
}}
h1, h2, h3 {{ color: #274E3C; border-bottom: 2px solid #5C7F63; padding-bottom: 6px; }}
table {{ border-collapse: collapse; width: 100%; margin: 20px 0; background: #FFFFFF; border-radius: 6px; overflow: hidden; }}
th, td {{ border: 1px solid #D9D7C7; padding: 10px 14px; text-align: left; }}
th {{ background-color: #274E3C; color: #FFFFFF; font-weight: bold; }}
tr:nth-child(even) {{ background-color: #FAFAF7; }}
blockquote {{ padding: 12px 18px; color: #274E3C; border-left: 5px solid #274E3C; background: #EAE8DE; margin: 18px 0; border-radius: 0 6px 6px 0; }}
code {{ background-color: #E6E4D8; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; color: #B8473F; font-size: 0.9em; }}
hr {{ border: 0; border-top: 1px solid #D9D7C7; margin: 25px 0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
            temp_html = proofs_dir / "temp_report.html"
            temp_html.write_text(styled_html, encoding="utf-8")

            page.goto(temp_html.as_uri())
            page.wait_for_timeout(1000)
            report_png = proofs_dir / "proof_02_analysis_report.png"
            page.screenshot(path=str(report_png), full_page=True)
            print(f"  [+] Saved Analysis Report proof: {report_png.name} ({report_png.stat().st_size:,} bytes)")

            if temp_html.exists():
                temp_html.unlink()

        browser.close()

    # 3. Create a Consolidated 6-Chart Montage Proof
    chart_names = [
        "daily_fire_activity.png",
        "confidence_distribution.png",
        "frp_distribution.png",
        "day_night_distribution.png",
        "satellite_sensor_distribution.png",
        "hotspot_priority_distribution.png",
    ]

    images = []
    for c_name in chart_names:
        c_path = charts_dir / c_name
        if c_path.exists():
            img = Image.open(c_path)
            images.append((c_name, img))

    if len(images) == 6:
        print("Assembling consolidated 6-chart grid montage...")
        # 3 rows x 2 cols
        target_w = 900
        resized = []
        for name, img in images:
            aspect = img.height / img.width
            w = target_w
            h = int(w * aspect)
            resized.append(img.resize((w, h), Image.Resampling.LANCZOS))

        # Layout: 3 rows of 2 images
        col1_w = max(resized[0].width, resized[2].width, resized[4].width)
        col2_w = max(resized[1].width, resized[3].width, resized[5].width)
        row1_h = max(resized[0].height, resized[1].height)
        row2_h = max(resized[2].height, resized[3].height)
        row3_h = max(resized[4].height, resized[5].height)

        total_width = col1_w + col2_w + 30
        total_height = row1_h + row2_h + row3_h + 40

        montage = Image.new("RGB", (total_width, total_height), color=(246, 245, 239))
        montage.paste(resized[0], (10, 10))
        montage.paste(resized[1], (col1_w + 20, 10))
        montage.paste(resized[2], (10, row1_h + 20))
        montage.paste(resized[3], (col1_w + 20, row1_h + 20))
        montage.paste(resized[4], (10, row1_h + row2_h + 30))
        montage.paste(resized[5], (col1_w + 20, row1_h + row2_h + 30))

        charts_proof_png = proofs_dir / "proof_03_charts_overview.png"
        montage.save(charts_proof_png, quality=92)
        print(f"  [+] Saved Charts Montage proof: {charts_proof_png.name} ({charts_proof_png.stat().st_size:,} bytes)")

    print(f"\nAll proofs successfully saved to: {proofs_dir}")

if __name__ == "__main__":
    main()
