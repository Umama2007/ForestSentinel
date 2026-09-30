"""Visualizer module for ForestSentinel.

Generates high-quality static charts (Matplotlib/Seaborn) with ForestSentinel styling
and an interactive Folium HTML map artifact showing fire detections and priority zones.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import folium
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/CLI environments
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)

# ForestSentinel Design Palette
PALETTE = {
    "dark_green": "#274E3C",
    "medium_green": "#5C7F63",
    "bg_warm": "#F6F5EF",
    "warning_amber": "#D79A32",
    "high_priority_red": "#B8473F",
    "low_priority_green": "#5C8A69",
    "dark_text": "#1E2A22",
    "muted_gray": "#78877E",
}


class Visualizer:
    """Renders static charts and interactive spatial artifacts for ForestSentinel."""

    def __init__(self, output_dir: Path) -> None:
        """Initialize visualizer with target output directory.

        Args:
            output_dir: Directory where chart PNGs and HTML map will be saved.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._apply_style()

    @staticmethod
    def _apply_style() -> None:
        """Apply consistent typography and color aesthetics to Matplotlib figures."""
        plt.rcParams.update({
            "figure.facecolor": PALETTE["bg_warm"],
            "axes.facecolor": PALETTE["bg_warm"],
            "axes.edgecolor": PALETTE["medium_green"],
            "axes.labelcolor": PALETTE["dark_text"],
            "text.color": PALETTE["dark_text"],
            "xtick.color": PALETTE["dark_text"],
            "ytick.color": PALETTE["dark_text"],
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Helvetica", "Arial"],
            "grid.color": "#E3E0D3",
            "grid.linestyle": "--",
            "grid.alpha": 0.7,
        })

    def plot_daily_fire_activity(self, df: pd.DataFrame) -> Path:
        """Generate line chart of active-fire detections over time."""
        fig, ax = plt.subplots(figsize=(10, 5))

        daily_counts = df.groupby("detection_date").size().reset_index(name="count")
        daily_counts = daily_counts.sort_values(by="detection_date")

        ax.plot(
            daily_counts["detection_date"],
            daily_counts["count"],
            marker="o",
            markersize=7,
            linewidth=2.5,
            color=PALETTE["dark_green"],
            label="Active-fire detections",
        )
        ax.fill_between(
            range(len(daily_counts)),
            daily_counts["count"],
            color=PALETTE["medium_green"],
            alpha=0.18,
        )

        for _, row in daily_counts.iterrows():
            ax.annotate(
                f"{row['count']}",
                (row["detection_date"], row["count"]),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=9,
                fontweight="bold",
                color=PALETTE["dark_green"],
            )

        ax.set_title("Daily Active-Fire Detections Trend (Amazon Pilot Region)", fontsize=13, fontweight="bold", pad=14)
        ax.set_xlabel("Observation Date (UTC)", fontsize=10, labelpad=8)
        ax.set_ylabel("Detection Count", fontsize=10, labelpad=8)
        ax.grid(True, axis="y")
        plt.xticks(rotation=25, ha="right")
        plt.tight_layout()

        output_path = self.output_dir / "daily_fire_activity.png"
        fig.savefig(output_path, dpi=200)
        plt.close(fig)
        return output_path

    def plot_confidence_distribution(self, df: pd.DataFrame) -> Path:
        """Generate bar chart showing the distribution of confidence ratings."""
        fig, ax = plt.subplots(figsize=(8, 5))

        conf_counts = df["confidence"].fillna("unknown").value_counts().reset_index()
        conf_counts.columns = ["confidence", "count"]

        colors = [
            PALETTE["high_priority_red"] if c == "high"
            else PALETTE["warning_amber"] if c == "nominal"
            else PALETTE["low_priority_green"]
            for c in conf_counts["confidence"].str.lower()
        ]

        bars = ax.bar(conf_counts["confidence"], conf_counts["count"], color=colors, width=0.55, edgecolor="#FFFFFF")

        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{height} ({height / len(df):.1%})",
                (bar.get_x() + bar.get_width() / 2, height),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=9,
                fontweight="bold",
            )

        ax.set_title("Distribution of Detection Confidence Levels", fontsize=13, fontweight="bold", pad=14)
        ax.set_xlabel("Confidence Rating", fontsize=10, labelpad=8)
        ax.set_ylabel("Count", fontsize=10, labelpad=8)
        ax.grid(True, axis="y")
        plt.tight_layout()

        output_path = self.output_dir / "confidence_distribution.png"
        fig.savefig(output_path, dpi=200)
        plt.close(fig)
        return output_path

    def plot_frp_distribution(self, df: pd.DataFrame) -> Path:
        """Generate histogram / distribution of Fire Radiative Power (MW)."""
        fig, ax = plt.subplots(figsize=(9, 5))

        frp_data = df["frp"].dropna()
        if frp_data.empty:
            ax.text(
                0.5, 0.5,
                "Fire Radiative Power (FRP) data not available for this dataset.",
                ha="center", va="center", fontsize=12, color=PALETTE["muted_gray"]
            )
            ax.set_title("Fire Radiative Power (FRP) Distribution - Not Available", fontsize=13, pad=14)
        else:
            sns.histplot(
                frp_data,
                bins=30,
                kde=True,
                color=PALETTE["warning_amber"],
                edgecolor="#FFFFFF",
                ax=ax,
            )
            mean_frp = frp_data.mean()
            median_frp = frp_data.median()
            ax.axvline(mean_frp, color=PALETTE["high_priority_red"], linestyle="--", linewidth=1.8, label=f"Mean: {mean_frp:.1f} MW")
            ax.axvline(median_frp, color=PALETTE["dark_green"], linestyle=":", linewidth=2.0, label=f"Median: {median_frp:.1f} MW")
            ax.set_title("Fire Radiative Power (FRP) Distribution", fontsize=13, fontweight="bold", pad=14)
            ax.set_xlabel("Fire Radiative Power (Megawatts)", fontsize=10, labelpad=8)
            ax.set_ylabel("Frequency", fontsize=10, labelpad=8)
            ax.legend(frameon=True, facecolor="#FFFFFF")
            ax.grid(True, axis="y")

        plt.tight_layout()
        output_path = self.output_dir / "frp_distribution.png"
        fig.savefig(output_path, dpi=200)
        plt.close(fig)
        return output_path

    def plot_day_night_distribution(self, df: pd.DataFrame) -> Path:
        """Generate donut chart of day vs night detections."""
        fig, ax = plt.subplots(figsize=(7, 5))

        dn_counts = df["daynight"].value_counts(dropna=False)
        labels = ["Day (D)" if str(k) == "D" else "Night (N)" if str(k) == "N" else "Unknown" for k in dn_counts.index]
        colors = [PALETTE["warning_amber"], PALETTE["dark_green"], PALETTE["muted_gray"]][:len(labels)]

        wedges, texts, autotexts = ax.pie(
            dn_counts.values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=140,
            colors=colors,
            wedgeprops={"edgecolor": "#FFFFFF", "linewidth": 2, "width": 0.45},
            textprops={"fontsize": 10, "color": PALETTE["dark_text"]},
        )
        for autotext in autotexts:
            autotext.set_fontweight("bold")
            autotext.set_color("#FFFFFF")

        ax.set_title("Day vs. Night Observation Split", fontsize=13, fontweight="bold", pad=14)
        plt.tight_layout()

        output_path = self.output_dir / "day_night_distribution.png"
        fig.savefig(output_path, dpi=200)
        plt.close(fig)
        return output_path

    def plot_satellite_sensor_distribution(self, df: pd.DataFrame) -> Path:
        """Generate bar chart comparing detections across satellites and instruments."""
        fig, ax = plt.subplots(figsize=(9, 5))

        grouping = (
            df.groupby(["satellite", "instrument"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(by="count", ascending=False)
        )
        grouping["label"] = grouping["satellite"].fillna("Unknown") + " (" + grouping["instrument"].fillna("Unknown") + ")"

        bars = ax.barh(grouping["label"], grouping["count"], color=PALETTE["medium_green"], edgecolor="#FFFFFF", height=0.55)

        for bar in bars:
            width = bar.get_width()
            ax.annotate(
                f"{width}",
                (width, bar.get_y() + bar.get_height() / 2),
                textcoords="offset points",
                xytext=(6, 0),
                va="center",
                fontsize=9,
                fontweight="bold",
                color=PALETTE["dark_green"],
            )

        ax.set_title("Detections by Satellite Platform & Sensor", fontsize=13, fontweight="bold", pad=14)
        ax.set_xlabel("Detection Count", fontsize=10, labelpad=8)
        ax.grid(True, axis="x")
        ax.invert_yaxis()
        plt.tight_layout()

        output_path = self.output_dir / "satellite_sensor_distribution.png"
        fig.savefig(output_path, dpi=200)
        plt.close(fig)
        return output_path

    def plot_hotspot_priority_distribution(self, grid_df: pd.DataFrame) -> Path:
        """Generate bar charts of grid cell priority classifications and top cells."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

        # 1. Priority Category Counts
        category_order = ["Low Priority", "Medium Priority", "High Priority"]
        cat_counts = grid_df["priority_label"].value_counts().reindex(category_order, fill_value=0)

        bar_colors = [PALETTE["low_priority_green"], PALETTE["warning_amber"], PALETTE["high_priority_red"]]
        bars1 = ax1.bar(category_order, cat_counts.values, color=bar_colors, edgecolor="#FFFFFF", width=0.5)

        for bar in bars1:
            h = bar.get_height()
            ax1.annotate(
                f"{h}",
                (bar.get_x() + bar.get_width() / 2, h),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=10,
                fontweight="bold",
            )

        ax1.set_title("Grid Cells by Priority Classification", fontsize=12, fontweight="bold", pad=12)
        ax1.set_ylabel("Number of Populated Cells", fontsize=10)
        ax1.grid(True, axis="y")

        # 2. Top 8 Grid Cells by Priority Score
        top_cells = grid_df.head(8)
        top_colors = [
            PALETTE["high_priority_red"] if lbl == "High Priority"
            else PALETTE["warning_amber"] if lbl == "Medium Priority"
            else PALETTE["low_priority_green"]
            for lbl in top_cells["priority_label"]
        ]
        bars2 = ax2.barh(top_cells["grid_id"], top_cells["priority_score"], color=top_colors, edgecolor="#FFFFFF", height=0.6)

        for bar in bars2:
            w = bar.get_width()
            ax2.annotate(
                f"{w:.1f}",
                (w, bar.get_y() + bar.get_height() / 2),
                textcoords="offset points",
                xytext=(6, 0),
                va="center",
                fontsize=9,
                fontweight="bold",
            )

        ax2.set_title("Top Hotspot Grid Cells by Priority Score", fontsize=12, fontweight="bold", pad=12)
        ax2.set_xlabel("Priority Score (0 - 100)", fontsize=10)
        ax2.set_xlim(0, 105)
        ax2.grid(True, axis="x")
        ax2.invert_yaxis()

        plt.tight_layout()
        output_path = self.output_dir / "hotspot_priority_distribution.png"
        fig.savefig(output_path, dpi=200)
        plt.close(fig)
        return output_path

    def render_folium_map(
        self,
        detections_df: pd.DataFrame,
        grid_df: pd.DataFrame,
        grid_size: float = 0.25,
    ) -> Path:
        """Render interactive Folium HTML map artifact showing fire detections and priority zones.

        Args:
            detections_df: Cleaned detections with grid_id and detection fields.
            grid_df: Enriched grid cells with priority_score and priority_label.
            grid_size: Grid cell dimension in decimal degrees.

        Returns:
            Path to generated fire_activity_map.html.
        """
        # Map center
        avg_lat = float(detections_df["latitude"].mean())
        avg_lon = float(detections_df["longitude"].mean())

        m = folium.Map(
            location=[avg_lat, avg_lon],
            zoom_start=7,
            tiles="OpenStreetMap",
            control_scale=True,
        )

        # Build priority lookup map
        priority_lookup = grid_df.set_index("grid_id")[["priority_label", "priority_score", "score_explanation"]].to_dict(orient="index")

        # Color mapping helper
        def get_color(label: str) -> str:
            if label == "High Priority":
                return PALETTE["high_priority_red"]
            elif label == "Medium Priority":
                return PALETTE["warning_amber"]
            return PALETTE["low_priority_green"]

        # 1. Add Grid Cell Rectangles
        grid_feature_group = folium.FeatureGroup(name="Hotspot Priority Grid Cells (0.25°)")
        for _, cell in grid_df.iterrows():
            g_lat = cell["grid_lat"]
            g_lon = cell["grid_lon"]
            lbl = cell["priority_label"]
            score = cell["priority_score"]
            count = cell["detection_count"]
            color = get_color(lbl)

            bounds = [[g_lat, g_lon], [g_lat + grid_size, g_lon + grid_size]]
            cell_popup_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 12px; width: 230px;">
                <b style="color: {color}; font-size: 14px;">{cell['grid_id']}</b><br>
                <b>Priority Classification:</b> <span style="color: {color}; font-weight: bold;">{lbl}</span><br>
                <b>Priority Score:</b> {score:.1f} / 100<br>
                <b>Total Detections:</b> {count}<br>
                <b>Recent (48h):</b> {cell['recent_detection_count']}<br>
                <b>Mean FRP:</b> {cell['mean_frp']:.1f} MW<br>
                <hr style="margin: 6px 0; border: 0; border-top: 1px solid #ccc;">
                <small style="color: #555;">{cell['score_explanation']}</small>
            </div>
            """

            folium.Rectangle(
                bounds=bounds,
                color=color,
                weight=1.5,
                fill=True,
                fill_color=color,
                fill_opacity=0.15 if lbl == "Low Priority" else 0.25 if lbl == "Medium Priority" else 0.40,
                popup=folium.Popup(cell_popup_html, max_width=280),
                tooltip=f"{cell['grid_id']} - {lbl} (Score: {score:.1f})",
            ).add_to(grid_feature_group)

        grid_feature_group.add_to(m)

        # 2. Add Active-Fire Detection Points
        points_group = folium.FeatureGroup(name="NASA FIRMS Active-Fire Detections")
        for _, row in detections_df.iterrows():
            lat = row["latitude"]
            lon = row["longitude"]
            gid = row.get("grid_id", "unknown")
            info = priority_lookup.get(gid, {"priority_label": "Low Priority", "priority_score": 0.0})
            lbl = info["priority_label"]
            score = info["priority_score"]
            color = get_color(lbl)

            dt_str = row["acq_datetime"].strftime("%Y-%m-%d %H:%M UTC") if pd.notna(row.get("acq_datetime")) else "N/A"
            frp_str = f"{row['frp']:.1f} MW" if pd.notna(row.get("frp")) else "N/A"
            conf = row.get("confidence") or "N/A"
            sat = row.get("satellite") or "N/A"
            inst = row.get("instrument") or "N/A"

            popup_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 11px; width: 220px;">
                <b style="color: {PALETTE['dark_green']}; font-size: 12px;">Active-Fire Detection</b><br>
                <b>Observation:</b> {dt_str}<br>
                <b>Coordinates:</b> {lat:.4f}, {lon:.4f}<br>
                <b>Confidence:</b> {conf}<br>
                <b>FRP:</b> {frp_str}<br>
                <b>Sensor:</b> {sat} ({inst})<br>
                <hr style="margin: 4px 0; border: 0; border-top: 1px solid #ccc;">
                <b>Grid Zone:</b> {gid}<br>
                <b>Zone Priority:</b> <span style="color: {color}; font-weight: bold;">{lbl} ({score:.1f})</span>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=4.5,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                weight=1,
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=f"Observation: {dt_str} | FRP: {frp_str}",
            ).add_to(points_group)

        points_group.add_to(m)

        # 3. Add Custom Floating HTML Legend & Scientific Limitation Note
        legend_html = f"""
        <div style="
            position: fixed;
            bottom: 25px;
            left: 25px;
            z-index: 9999;
            background-color: white;
            padding: 14px 18px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            font-family: Arial, sans-serif;
            font-size: 12px;
            line-height: 1.5;
            max-width: 320px;
        ">
            <h4 style="margin: 0 0 6px 0; color: {PALETTE['dark_green']}; font-size: 13px;">
                ForestSentinel Fire Priority Zones
            </h4>
            <div style="display: flex; align-items: center; margin-bottom: 4px;">
                <span style="background: {PALETTE['high_priority_red']}; width: 14px; height: 14px; display: inline-block; margin-right: 8px; border-radius: 2px;"></span>
                <b>High Priority</b> (Score ≥ 70)
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 4px;">
                <span style="background: {PALETTE['warning_amber']}; width: 14px; height: 14px; display: inline-block; margin-right: 8px; border-radius: 2px;"></span>
                <b>Medium Priority</b> (Score 35 – 69)
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="background: {PALETTE['low_priority_green']}; width: 14px; height: 14px; display: inline-block; margin-right: 8px; border-radius: 2px;"></span>
                <b>Low Priority</b> (Score &lt; 35)
            </div>
            <hr style="margin: 6px 0; border: 0; border-top: 1px solid #eee;">
            <p style="margin: 0; font-size: 10px; color: #666;">
                <b>Scientific Notice:</b> NASA FIRMS records active-fire / thermal-anomaly detections.
                Priority labels are analytical rankings, not wildfire predictions or emergency warnings.
            </p>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))
        folium.LayerControl().add_to(m)

        output_path = self.output_dir / "fire_activity_map.html"
        m.save(str(output_path))
        logger.info("Saved interactive Folium map artifact to: %s", output_path)
        return output_path

    def render_all(
        self,
        detections_df: pd.DataFrame,
        grid_df: pd.DataFrame,
        grid_size: float = 0.25,
    ) -> Dict[str, Path]:
        """Generate all 6 static charts and the interactive Folium HTML map artifact.

        Returns:
            Dictionary mapping artifact names to their file paths.
        """
        logger.info("Generating static visualizations and Folium map artifact in '%s'...", self.output_dir)

        artifacts = {
            "daily_fire_activity": self.plot_daily_fire_activity(detections_df),
            "confidence_distribution": self.plot_confidence_distribution(detections_df),
            "frp_distribution": self.plot_frp_distribution(detections_df),
            "day_night_distribution": self.plot_day_night_distribution(detections_df),
            "satellite_sensor_distribution": self.plot_satellite_sensor_distribution(detections_df),
            "hotspot_priority_distribution": self.plot_hotspot_priority_distribution(grid_df),
            "fire_activity_map": self.render_folium_map(detections_df, grid_df, grid_size),
        }
        logger.info("Successfully generated all %d visual artifacts.", len(artifacts))
        return artifacts
