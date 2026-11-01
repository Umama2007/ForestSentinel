"""Generate clean, publication-grade README visual assets for ForestSentinel."""

from __future__ import annotations

import asyncio
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image

BASE_DIR = Path(__file__).parent.parent.resolve()
DOCS_ASSETS = BASE_DIR / "docs" / "assets"
DOCS_ASSETS.mkdir(parents=True, exist_ok=True)

# ForestSentinel Palette
NAVY_BG = "#0B132B"
CARD_BG = "#1C2541"
BORDER_COLOR = "#3A506B"
ACCENT_GREEN = "#2A9D8F"
ACCENT_FIRE = "#FF6B35"
ACCENT_AMBER = "#FFB703"
TEXT_WHITE = "#F8F9FA"
TEXT_MUTED = "#8D99AE"
ARROW_COLOR = "#5BC0BE"


def render_architecture_diagram():
    """Render a clean, modern, professional architecture diagram image."""
    fig, ax = plt.subplots(figsize=(14, 8), dpi=200, facecolor=NAVY_BG)
    ax.set_facecolor(NAVY_BG)
    ax.set_xlim(0, 1400)
    ax.set_ylim(0, 800)
    ax.axis("off")

    # Title & Subtitle
    ax.text(
        700, 750,
        "ForestSentinel End-to-End System Architecture",
        ha="center", va="center",
        fontsize=18, fontweight="bold",
        color=TEXT_WHITE,
    )
    ax.text(
        700, 720,
        "Data Engineering Pipeline, Hotspot Spatial Tessellation & Privacy-Safe Conservation Exposure",
        ha="center", va="center",
        fontsize=11, color=TEXT_MUTED,
    )

    # 7 Main Pipeline Stages: x, y, width, height, title, subtitle, tech, color
    stages = [
        # Col 1: Part 1 Ingestion
        (80, 520, 260, 130, "1. Ingestion & Raw Archive", "NASA FIRMS NRT Area API\nArea CSV Download & Hash Verification\nZero-Loss Local Storage", "Requests / Area API", "#E63946"),
        (400, 520, 260, 130, "2. Cleaning & Validation", "Pandas Coordinate / Time Cleaning\nPydantic v2 Schema Enforcement\nDefensive Rejection Isolation", "Pandas + Pydantic v2", "#FF6B35"),
        (720, 520, 260, 130, "3. Cloud Persistence", "Supabase Postgres\nDeterministic SHA-256 Key Deduplication\nBatched REST Inserts", "Supabase", "#FFB703"),

        # Col 2: Part 2 Analytics
        (1040, 520, 260, 130, "4. Hotspot Tessellation", "0.25° Geographic Spatial Tessellation\nFrequency, Recency, FRP, Confidence\nExplainable Fire Priority (0-100)", "NumPy + PriorityScorer", "#2A9D8F"),

        # Row 2: Part 3 & Outputs
        (1040, 280, 260, 130, "5. Conservation Analysis", "GBIF Animal Occurrence Ingestion\nSpecies-Level Deduplication\nVerified IUCN Red List Enrichment", "GBIF + IUCN Red List v4", "#4CC9F0"),
        (560, 280, 420, 130, "6. Conservation Scoring & Caching", "Explainable Conservation Score (0-100)\nFirestore Collection: species_grid_summaries\nFirestore Collection: conservation_assessments", "ConservationScorer + Firestore", "#5C7F63"),
        (80, 280, 420, 130, "7. Privacy-Safe Intelligence", "Aggregated 0.25° Interactive Folium Maps\nStatic Matplotlib / Seaborn PNG Charts\nStructured JSON & Markdown Audit Reports", "Folium + Matplotlib + JSON/MD", "#8D99AE"),
    ]

    for x, y, w, h, title, body, tech, accent in stages:
        # Card background
        rect = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.0,rounding_size=12",
            facecolor=CARD_BG,
            edgecolor=BORDER_COLOR,
            linewidth=1.2,
        )
        ax.add_patch(rect)

        # Top accent stripe
        stripe = patches.FancyBboxPatch(
            (x, y + h - 6), w, 6,
            boxstyle="round,pad=0.0,rounding_size=3",
            facecolor=accent,
            edgecolor="none",
        )
        ax.add_patch(stripe)

        # Text inside card
        ax.text(x + 15, y + h - 22, title, fontsize=10.5, fontweight="bold", color=TEXT_WHITE, va="top")
        ax.text(x + 15, y + h - 45, body, fontsize=8.5, color="#D0D6DF", va="top", linespacing=1.35)
        ax.text(x + 15, y + 14, f"Tech: {tech}", fontsize=7.5, fontweight="bold", color=accent, va="bottom")

    # Arrows between stages
    def draw_arrow(x1, y1, x2, y2, label=""):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="-|>",
                color=ARROW_COLOR,
                lw=2.0,
                mutation_scale=15,
            )
        )
        if label:
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2 + 10
            ax.text(mid_x, mid_y, label, fontsize=8, color=ARROW_COLOR, ha="center", va="center", fontweight="bold")

    # Flow arrows
    draw_arrow(340, 585, 400, 585)      # 1 -> 2
    draw_arrow(660, 585, 720, 585)      # 2 -> 3
    draw_arrow(980, 585, 1040, 585)     # 3 -> 4
    draw_arrow(1170, 520, 1170, 410)    # 4 -> 5
    draw_arrow(1040, 345, 980, 345)     # 5 -> 6
    draw_arrow(560, 345, 500, 345)      # 6 -> 7

    # Privacy & Safety Banner at bottom
    banner_rect = patches.FancyBboxPatch(
        (80, 80), 1220, 120,
        boxstyle="round,pad=0.0,rounding_size=10",
        facecolor="#101A30",
        edgecolor="#2A9D8F",
        linewidth=1.2,
    )
    ax.add_patch(banner_rect)

    ax.text(
        110, 160,
        "🔒 CORE DATA PRIVACY & SCIENTIFIC ETHICS GUARANTEES",
        fontsize=10.5, fontweight="bold", color="#2A9D8F", va="top"
    )
    banner_text = (
        "• Strict Wildlife Privacy: Zero raw occurrence coordinates (lat/lon) are ever saved in Firestore, exported, reported, or plotted.\n"
        "• Geographic Aggregation: All wildlife observations are strictly aggregated to 0.25° geographic grid cells (~27.7 km at equator).\n"
        "• Scientific Accuracy: Conservation Exposure is an analytical overlap indicator, not confirmed animal harm or predictive wildfire spread.\n"
        "• Verified Integrity: IUCN statuses are strictly verified through official API; unverified statuses are marked as unavailable without guessing."
    )
    ax.text(110, 135, banner_text, fontsize=8.5, color=TEXT_WHITE, va="top", linespacing=1.4)

    plt.tight_layout()
    out_path = DOCS_ASSETS / "architecture.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=NAVY_BG)
    plt.close(fig)
    print(f"[OK] Saved architecture diagram: {out_path}")


async def capture_html_preview(html_path: Path, output_png: Path, title_caption: str):
    """Render a clean headless browser screenshot of an HTML map and add caption."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 780})
        await page.goto(f"file:///{html_path.resolve().as_posix()}", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        temp_screenshot = output_png.parent / f"temp_{output_png.name}"
        await page.screenshot(path=str(temp_screenshot))
        await browser.close()

    # Load with PIL, add top/bottom banner with disclaimer
    img = Image.open(temp_screenshot)
    fig, ax = plt.subplots(figsize=(12, 7.5), dpi=150, facecolor="#F6F5EF")
    ax.imshow(img)
    ax.axis("off")

    plt.title(title_caption, fontsize=11, fontweight="bold", color="#1E2A22", pad=12)
    plt.tight_layout()
    fig.savefig(output_png, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if temp_screenshot.exists():
        temp_screenshot.unlink()

    print(f"[OK] Saved map preview: {output_png}")


async def main():
    print("[*] Generating README visual proof assets...")
    # 1. Architecture diagram
    render_architecture_diagram()

    # 2. Fire Activity Map Preview
    part2_map = BASE_DIR / "reports" / "charts" / "20260930_102826" / "fire_activity_map.html"
    if part2_map.exists():
        await capture_html_preview(
            html_path=part2_map,
            output_png=DOCS_ASSETS / "fire_activity_map_preview.png",
            title_caption="NASA FIRMS active-fire detections and analytical priority zones. Not a wildfire prediction."
        )

    # 3. Conservation Exposure Map Preview
    cons_dirs = sorted((BASE_DIR / "reports" / "conservation").glob("20*"))
    if cons_dirs:
        part3_map = cons_dirs[-1] / "conservation_exposure_map.html"
        if part3_map.exists():
            await capture_html_preview(
                html_path=part3_map,
                output_png=DOCS_ASSETS / "conservation_exposure_preview.png",
                title_caption="ForestSentinel Conservation Exposure Overlay: 0.25° Grid Aggregation. Reflects recorded occurrences, not proof of harm."
            )

    print("[*] All assets generated successfully!")


if __name__ == "__main__":
    asyncio.run(main())
