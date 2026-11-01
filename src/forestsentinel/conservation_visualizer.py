"""Conservation Visualizer module for ForestSentinel.

Generates privacy-safe charts and an interactive Folium conservation exposure map artifact.
STRICT PRIVACY GUARANTEE: Never renders individual animal observation points or exact coordinates.
Only renders aggregated geographic grid cells (0.25 degree resolution).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import folium
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)

# ForestSentinel Conservation Design Palette - dark theme matching the web dashboard.
PALETTE = {
    "dark_green": "#34d399",
    "medium_green": "#22d3ee",
    "bg_warm": "#080e1b",
    "warning_amber": "#fbbf24",       # Medium fire priority
    "high_priority_red": "#f87171",
    "low_priority_green": "#64748b",
    "dark_text": "#f8fafc",
    "muted_gray": "#98a5ba",
    "cr_red": "#ef4444",
    "en_orange": "#fb923c",
    "vu_yellow": "#facc15",
    "card_bg": "#0d1423",
    "grid_line": "#1e293b",
}

# Light palette for the interactive Folium map (OpenStreetMap basemap).
MAP_PALETTE = {
    "dark_green": "#274E3C",
    "medium_green": "#5C7F63",
    "bg_warm": "#F6F5EF",
    "warning_amber": "#D79A32",
    "high_priority_red": "#B8473F",
    "low_priority_green": "#5C8A69",
    "dark_text": "#1E2A22",
    "muted_gray": "#78877E",
    "cr_red": "#D90429",
    "en_orange": "#F77F00",
    "vu_yellow": "#E5A93C",
    "card_bg": "#FFFFFF",
    "grid_line": "#E2E0D8",
}


class ConservationVisualizer:
    """Renders privacy-safe conservation exposure charts and Folium map layer."""

    def __init__(self, output_dir: Path) -> None:
        """Initialize with destination output directory.

        Args:
            output_dir: Directory where PNG charts and Folium map will be saved.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._apply_style()

    @staticmethod
    def _apply_style() -> None:
        """Apply consistent typography and aesthetic styling to Matplotlib figures."""
        plt.rcParams.update({
            "figure.facecolor": PALETTE["bg_warm"],
            "axes.facecolor": PALETTE["bg_warm"],
            "axes.edgecolor": PALETTE["grid_line"],
            "axes.labelcolor": PALETTE["muted_gray"],
            "axes.titlecolor": PALETTE["dark_text"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.axisbelow": True,
            "text.color": PALETTE["dark_text"],
            "xtick.color": PALETTE["muted_gray"],
            "ytick.color": PALETTE["muted_gray"],
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"],
            "grid.color": PALETTE["grid_line"],
            "grid.linestyle": "-",
            "grid.alpha": 1.0,
            "legend.facecolor": PALETTE["card_bg"],
            "legend.edgecolor": PALETTE["grid_line"],
            "legend.labelcolor": PALETTE["dark_text"],
            "savefig.facecolor": PALETTE["bg_warm"],
        })

    def render_threatened_species_by_category(
        self,
        threatened_by_cat: Dict[str, int],
    ) -> Path:
        """Render bar chart of verified threatened species counts by IUCN category (CR, EN, VU).

        Args:
            threatened_by_cat: Dictionary with counts for 'CR', 'EN', 'VU'.

        Returns:
            Path to saved PNG image.
        """
        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)

        categories = ["Critically Endangered\n(CR)", "Endangered\n(EN)", "Vulnerable\n(VU)"]
        keys = ["CR", "EN", "VU"]
        counts = [int(threatened_by_cat.get(k, 0)) for k in keys]
        bar_colors = [PALETTE["cr_red"], PALETTE["en_orange"], PALETTE["vu_yellow"]]

        bars = ax.bar(categories, counts, color=bar_colors, width=0.5, edgecolor=PALETTE["bg_warm"], linewidth=1.2)

        # Label bars
        max_val = max(counts) if counts else 0
        ax.set_ylim(0, max(max_val + 2, 5))

        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{int(height)}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontweight="bold",
                fontsize=11,
                color=PALETTE["dark_text"],
            )

        ax.set_title(
            "Verified Threatened Animal Species by IUCN Category\n(Recorded Occurrences in Fire Priority Zones)",
            fontsize=12,
            fontweight="bold",
            pad=14,
        )
        ax.set_ylabel("Unique Species Count", fontsize=10, labelpad=8)
        ax.grid(axis="y")

        if max_val == 0:
            ax.text(
                0.5, 0.5,
                "No threatened-species classifications are available in this run\nbecause IUCN verification has not yet been configured.",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=10,
                color=PALETTE["muted_gray"],
                bbox=dict(boxstyle="round,pad=0.5", facecolor=PALETTE["card_bg"], edgecolor=PALETTE["muted_gray"], alpha=0.9),
            )

        plt.tight_layout()
        out_path = self.output_dir / "threatened_species_by_category.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        logger.info("Saved %s", out_path)
        return out_path

    def render_species_exposure_by_priority_zone(
        self,
        species_summaries: List[Dict[str, Any]],
    ) -> Path:
        """Render bar chart comparing threatened-species summaries in Medium vs High fire-activity cells.

        Args:
            species_summaries: List of scored species-grid summaries.

        Returns:
            Path to saved PNG image.
        """
        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)

        high_species = [s for s in species_summaries if s.get("grid_priority_label") == "High Priority" and s.get("iucn_verified") and s.get("iucn_category") in {"CR", "EN", "VU"}]
        med_species = [s for s in species_summaries if s.get("grid_priority_label") == "Medium Priority" and s.get("iucn_verified") and s.get("iucn_category") in {"CR", "EN", "VU"}]

        # All recorded animal species regardless of IUCN status
        all_high = [s for s in species_summaries if s.get("grid_priority_label") == "High Priority"]
        all_med = [s for s in species_summaries if s.get("grid_priority_label") == "Medium Priority"]

        zones = ["High Priority Fire Cells", "Medium Priority Fire Cells"]
        threatened_counts = [len(high_species), len(med_species)]
        total_counts = [len(all_high), len(all_med)]

        x = np.arange(len(zones))
        width = 0.35

        b1 = ax.bar(x - width/2, total_counts, width, label="All Animal Species Recorded", color=PALETTE["medium_green"], edgecolor=PALETTE["bg_warm"], linewidth=1.1)
        b2 = ax.bar(x + width/2, threatened_counts, width, label="Verified Threatened Species", color=PALETTE["high_priority_red"], edgecolor=PALETTE["bg_warm"], linewidth=1.1)

        ax.set_xticks(x)
        ax.set_xticklabels(zones, fontweight="bold", fontsize=10)
        ax.set_ylabel("Species-Grid Occurrence Count", fontsize=10, labelpad=8)
        ax.set_title(
            "Species Occurrence Exposure by Fire Activity Priority Zone",
            fontsize=12,
            fontweight="bold",
            pad=14,
        )
        ax.legend(frameon=True, facecolor=PALETTE["card_bg"], edgecolor=PALETTE["grid_line"], fontsize=9)
        ax.grid(axis="y")

        max_val = max(total_counts + threatened_counts) if (total_counts + threatened_counts) else 0
        ax.set_ylim(0, max(max_val + 3, 5))

        for b in list(b1) + list(b2):
            h = b.get_height()
            ax.annotate(
                f"{int(h)}",
                xy=(b.get_x() + b.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

        plt.tight_layout()
        out_path = self.output_dir / "species_exposure_by_priority_zone.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        logger.info("Saved %s", out_path)
        return out_path

    def render_top_conservation_priority_cells(
        self,
        cell_conservation_summaries: List[Dict[str, Any]],
    ) -> Path:
        """Render horizontal bar chart of top grid cells by conservation exposure score.

        Args:
            cell_conservation_summaries: List of cell conservation metric dictionaries.

        Returns:
            Path to saved PNG image.
        """
        fig, ax = plt.subplots(figsize=(9, 5), dpi=150)

        # Sort by fire score or max conservation exposure score
        sorted_cells = sorted(
            cell_conservation_summaries,
            key=lambda c: (
                c.get("max_conservation_exposure_score") or 0.0,
                c.get("fire_priority_score") or 0.0,
            ),
            reverse=True
        )[:10]

        if not sorted_cells:
            ax.text(0.5, 0.5, "No priority cells to display", ha="center", va="center", transform=ax.transAxes)
            out_path = self.output_dir / "top_conservation_priority_cells.png"
            fig.savefig(out_path, dpi=150)
            plt.close(fig)
            return out_path

        cell_ids = [c["grid_id"] for c in reversed(sorted_cells)]
        fire_scores = [float(c.get("fire_priority_score", 0.0)) for c in reversed(sorted_cells)]
        cons_scores = [float(c.get("max_conservation_exposure_score") or 0.0) for c in reversed(sorted_cells)]

        y = np.arange(len(cell_ids))
        height = 0.38

        b1 = ax.barh(y - height/2, fire_scores, height, label="Fire Activity Priority Score (Part 2)", color=PALETTE["warning_amber"], edgecolor=PALETTE["bg_warm"], linewidth=1.1)
        b2 = ax.barh(y + height/2, cons_scores, height, label="Conservation Exposure Priority Score (Part 3)", color=PALETTE["high_priority_red"], edgecolor=PALETTE["bg_warm"], linewidth=1.1)

        ax.set_yticks(y)
        ax.set_yticklabels(cell_ids, fontsize=9)
        ax.set_xlabel("Priority Score (0-100 Scale)", fontsize=10, labelpad=8)
        ax.set_xlim(0, 105)
        ax.set_title(
            "Priority Grid Cells: Fire Activity vs Conservation Exposure Scores",
            fontsize=12,
            fontweight="bold",
            pad=14,
        )
        ax.legend(frameon=True, facecolor=PALETTE["card_bg"], edgecolor=PALETTE["grid_line"], fontsize=9, loc="lower right")
        ax.grid(axis="x")

        for b in list(b1) + list(b2):
            w = b.get_width()
            if w > 0:
                ax.annotate(
                    f"{w:.1f}",
                    xy=(w, b.get_y() + b.get_height() / 2),
                    xytext=(4, 0),
                    textcoords="offset points",
                    ha="left",
                    va="center",
                    fontsize=8,
                    fontweight="bold",
                )

        plt.tight_layout()
        out_path = self.output_dir / "top_conservation_priority_cells.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        logger.info("Saved %s", out_path)
        return out_path

    def render_biodiversity_data_quality(
        self,
        analysis_metrics: Dict[str, Any],
    ) -> Path:
        """Render data quality & pipeline metrics chart for the biodiversity ingestion pipeline.

        Args:
            analysis_metrics: Summary metrics dictionary.

        Returns:
            Path to saved PNG image.
        """
        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)

        labels = [
            "GBIF Records\nReceived",
            "Unique Animal\nSpecies Found",
            "IUCN Statuses\nVerified",
            "Verified\nThreatened",
            "Pending IUCN\nVerification",
        ]

        values = [
            int(analysis_metrics.get("gbif_occurrence_records_received", 0)),
            int(analysis_metrics.get("unique_animal_species_found", 0)),
            int(analysis_metrics.get("species_with_verified_iucn_status", 0)),
            int(analysis_metrics.get("threatened_species_found", 0)),
            int(analysis_metrics.get("pending_iucn_verification_count", analysis_metrics.get("unverified_or_not_threatened_count", 0))),
        ]

        colors = [
            PALETTE["dark_green"],
            PALETTE["medium_green"],
            PALETTE["warning_amber"],
            PALETTE["high_priority_red"],
            PALETTE["muted_gray"],
        ]

        bars = ax.bar(labels, values, color=colors, width=0.5, edgecolor=PALETTE["bg_warm"], linewidth=1.2)

        max_val = max(values) if values else 0
        ax.set_ylim(0, max(max_val * 1.15, 10))

        for bar in bars:
            h = bar.get_height()
            ax.annotate(
                f"{int(h)}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontweight="bold",
                fontsize=10,
                color=PALETTE["dark_text"],
            )

        ax.set_title(
            "Biodiversity Data Pipeline Quality & Verification Funnel",
            fontsize=12,
            fontweight="bold",
            pad=14,
        )
        ax.set_ylabel("Record / Species Count", fontsize=10, labelpad=8)
        ax.grid(axis="y")

        plt.tight_layout()
        out_path = self.output_dir / "biodiversity_data_quality.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        logger.info("Saved %s", out_path)
        return out_path

    def render_folium_map(
        self,
        grid_cells_df: pd.DataFrame,
        cell_conservation_summaries: List[Dict[str, Any]],
        grid_size_degrees: float = 0.25,
    ) -> Path:
        """Render interactive Folium conservation exposure map artifact.

        CRITICAL PRIVACY RULE:
        - NEVER renders individual animal coordinates or occurrence points.
        - Only renders aggregated grid cells (rectangles).
        - Includes prominent ethics and responsible-use disclaimers.

        Args:
            grid_cells_df: Full Part 2 grid cells DataFrame (for spatial context).
            cell_conservation_summaries: Scored conservation metrics per cell.
            grid_size_degrees: Resolution of grid cells in degrees.

        Returns:
            Path to saved HTML map artifact.
        """
        # Build cell conservation lookup map
        cons_lookup: Dict[str, Dict[str, Any]] = {
            c["grid_id"]: c for c in cell_conservation_summaries
        }

        # Calculate map center
        if not grid_cells_df.empty:
            center_lat = float(grid_cells_df["center_lat"].mean())
            center_lon = float(grid_cells_df["center_lon"].mean())
        else:
            center_lat, center_lon = -8.0, -60.0

        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=7,
            tiles="OpenStreetMap",
            control_scale=True,
        )

        # Layer 1: Fire Priority Grid Cells (Part 2)
        fire_layer = folium.FeatureGroup(name="Fire Activity Priority Zones", show=True)
        # Layer 2: Conservation Exposure Overlay (Part 3)
        cons_layer = folium.FeatureGroup(name="Conservation Exposure Overlay", show=True)

        for _, row in grid_cells_df.iterrows():
            gid = str(row["grid_id"])
            min_lat = float(row["grid_lat"])
            min_lon = float(row["grid_lon"])
            max_lat = min_lat + grid_size_degrees
            max_lon = min_lon + grid_size_degrees

            bounds = [[min_lat, min_lon], [max_lat, max_lon]]
            priority_lbl = str(row.get("priority_label", "Low Priority"))
            fire_score = float(row.get("priority_score", 0.0))
            det_count = int(row.get("detection_count", 0))

            # Style by fire priority
            if priority_lbl == "High Priority":
                fill_color = MAP_PALETTE["high_priority_red"]
                fill_opacity = 0.40
                weight = 2
            elif priority_lbl == "Medium Priority":
                fill_color = MAP_PALETTE["warning_amber"]
                fill_opacity = 0.30
                weight = 1.5
            else:
                fill_color = MAP_PALETTE["low_priority_green"]
                fill_opacity = 0.15
                weight = 1

            popup_html = f"""
            <div style="font-family: sans-serif; font-size: 12px; width: 220px;">
                <h4 style="margin: 0 0 6px 0; color: #1E2A22;">{gid}</h4>
                <p style="margin: 2px 0;"><b>Fire Priority:</b> {priority_lbl}</p>
                <p style="margin: 2px 0;"><b>Fire Score:</b> {fire_score:.1f} / 100</p>
                <p style="margin: 2px 0;"><b>Active Detections:</b> {det_count}</p>
            </div>
            """

            folium.Rectangle(
                bounds=bounds,
                color=fill_color,
                weight=weight,
                fill=True,
                fill_color=fill_color,
                fill_opacity=fill_opacity,
                popup=folium.Popup(popup_html, max_width=250),
            ).add_to(fire_layer)

            # Check if this cell has conservation exposure data
            if gid in cons_lookup:
                cons_data = cons_lookup[gid]
                threatened_cnt = int(cons_data.get("threatened_species_count", 0))
                highest_cat = cons_data.get("highest_iucn_category")
                cons_label = cons_data.get("conservation_priority_label", "Pending IUCN Verification")
                max_score = cons_data.get("max_conservation_exposure_score")
                score_str = f"{max_score:.1f}" if max_score is not None else "Pending Verification"

                # If cell has threatened species or was analyzed
                has_threatened = threatened_cnt > 0
                stroke_color = MAP_PALETTE["cr_red"] if has_threatened else MAP_PALETTE["medium_green"]

                cons_popup_html = f"""
                <div style="font-family: sans-serif; font-size: 12px; width: 260px; line-height: 1.4;">
                    <h4 style="margin: 0 0 6px 0; color: #274E3C; border-bottom: 1px solid #CCC; padding-bottom: 4px;">
                        🌿 {gid} - Conservation Analysis
                    </h4>
                    <p style="margin: 3px 0;"><b>Fire Activity Priority:</b> {priority_lbl} ({fire_score:.1f})</p>
                    <p style="margin: 3px 0;"><b>Unique Animal Species Recorded:</b> {cons_data.get('total_species_recorded', 0)}</p>
                    <p style="margin: 3px 0;"><b>Verified Threatened Species:</b> <span style="color: {'#D90429' if has_threatened else '#5C7F63'}; font-weight: bold;">{threatened_cnt}</span></p>
                    <p style="margin: 3px 0;"><b>Highest Verified IUCN Status:</b> {highest_cat or 'Pending IUCN Verification'}</p>
                    <p style="margin: 3px 0;"><b>Conservation Exposure Score:</b> {score_str}</p>
                    <p style="margin: 3px 0;"><b>Exposure Label:</b> {cons_label}</p>
                    <div style="margin-top: 8px; font-size: 10px; color: #78877E; border-top: 1px dashed #DDD; padding-top: 4px;">
                        <b>Responsible Use Note:</b> Species data is aggregated to this 0.25° grid cell to protect wildlife. Reflects documented historical occurrences, not confirmed current presence.
                    </div>
                </div>
                """

                # Distinct highlighted overlay
                folium.Rectangle(
                    bounds=bounds,
                    color=stroke_color,
                    weight=3 if has_threatened else 2,
                    dash_array="5, 5" if not has_threatened else None,
                    fill=True,
                    fill_color="#2A9D8F" if not has_threatened else "#E63946",
                    fill_opacity=0.25 if has_threatened else 0.10,
                    popup=folium.Popup(cons_popup_html, max_width=290),
                    tooltip=f"{gid}: {threatened_cnt} threatened species recorded (Fire Score: {fire_score:.1f})",
                ).add_to(cons_layer)

        fire_layer.add_to(m)
        cons_layer.add_to(m)
        folium.LayerControl().add_to(m)

        # Floating Responsible-Use & Privacy Disclaimer Card
        disclaimer_html = """
        <div style="
            position: fixed;
            bottom: 25px;
            left: 25px;
            width: 380px;
            background-color: rgba(255, 255, 255, 0.95);
            border: 1px solid #78877E;
            border-left: 5px solid #274E3C;
            border-radius: 4px;
            padding: 10px 14px;
            font-family: sans-serif;
            font-size: 11px;
            line-height: 1.4;
            color: #1E2A22;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            z-index: 9999;
        ">
            <strong style="color: #274E3C; font-size: 12px;">🛡️ ForestSentinel Conservation Exposure Layer</strong><br/>
            <span style="font-size: 10.5px; color: #333;">
                Species information is aggregated to 0.25° grid cells for privacy and reflects recorded biodiversity occurrences, not confirmed current presence. Conservation exposure is an analytical indicator, not proof of harm.
            </span>
        </div>
        """
        m.get_root().html.add_child(folium.Element(disclaimer_html))

        out_path = self.output_dir / "conservation_exposure_map.html"
        m.save(str(out_path))
        logger.info("Saved interactive Folium conservation map: %s", out_path)
        return out_path

    def render_all(
        self,
        grid_cells_df: pd.DataFrame,
        analysis_results: Dict[str, Any],
        grid_size_degrees: float = 0.25,
    ) -> Dict[str, Path]:
        """Render all 4 static charts and the Folium map artifact.

        Args:
            grid_cells_df: Scored grid cells DataFrame.
            analysis_results: Results dict from ConservationAnalyzer.run_analysis.
            grid_size_degrees: Resolution of grid cells in degrees.

        Returns:
            Dictionary mapping artifact names to their filesystem paths.
        """
        artifacts: Dict[str, Path] = {}

        # 1. Threatened species by category
        threatened_by_cat = analysis_results.get("threatened_by_category", {"CR": 0, "EN": 0, "VU": 0})
        artifacts["threatened_species_by_category"] = self.render_threatened_species_by_category(threatened_by_cat)

        # 2. Species exposure by priority zone
        species_summaries = analysis_results.get("species_grid_summaries", [])
        artifacts["species_exposure_by_priority_zone"] = self.render_species_exposure_by_priority_zone(species_summaries)

        # 3. Top conservation priority cells
        cell_summaries = analysis_results.get("cell_conservation_summaries", [])
        artifacts["top_conservation_priority_cells"] = self.render_top_conservation_priority_cells(cell_summaries)

        # 4. Biodiversity data quality
        artifacts["biodiversity_data_quality"] = self.render_biodiversity_data_quality(analysis_results)

        # 5. Interactive Folium map
        artifacts["conservation_exposure_map"] = self.render_folium_map(
            grid_cells_df=grid_cells_df,
            cell_conservation_summaries=cell_summaries,
            grid_size_degrees=grid_size_degrees,
        )

        return artifacts
