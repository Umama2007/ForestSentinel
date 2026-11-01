"""
ForestSentinel Localhost Web Dashboard Server.

Serves an interactive executive and scientific console on http://localhost:8000
with embedded Folium geospatial maps, live analytics charts, and pipeline runners.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, render_template, send_file, send_from_directory, request

logger = logging.getLogger("forestsentinel.web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


def get_latest_file(pattern: str) -> Optional[Path]:
    """Find the most recent file matching a glob pattern relative to BASE_DIR."""
    matches = glob.glob(str(BASE_DIR / pattern))
    if not matches:
        return None
    matches.sort(key=os.path.getmtime, reverse=True)
    return Path(matches[0])


@app.route("/")
def index():
    """Render the ForestSentinel Localhost Dashboard."""
    return render_template("dashboard.html")


@app.route("/map/fire")
def map_fire():
    """Serve the latest interactive Folium Fire Activity & Priority Map."""
    map_path = get_latest_file("reports/charts/*/fire_activity_map.html")
    if not map_path or not map_path.exists():
        # Fallback to preview or placeholder
        return "<h3>Fire activity map not generated yet. Run Part 2 analysis.</h3>", 404
    return send_file(map_path, mimetype="text/html")


@app.route("/map/conservation")
def map_conservation():
    """Serve the latest interactive Folium Conservation Exposure Map."""
    map_path = get_latest_file("reports/conservation/*/conservation_exposure_map.html")
    if not map_path or not map_path.exists():
        return "<h3>Conservation exposure map not generated yet. Run Part 3 analysis.</h3>", 404
    return send_file(map_path, mimetype="text/html")


@app.route("/static/assets/<path:filename>")
def serve_docs_assets(filename: str):
    """Serve documentation and report assets."""
    assets_dir = BASE_DIR / "docs" / "assets"
    file_path = assets_dir / filename
    if file_path.exists():
        return send_from_directory(assets_dir, filename)

    # Check reports/proofs
    proofs_dir = BASE_DIR / "reports" / "proofs"
    if (proofs_dir / filename).exists():
        return send_from_directory(proofs_dir, filename)

    return "Asset not found", 404


def latest_run_dir(pattern: str) -> Optional[Path]:
    """Return the most recent timestamped run directory matching a glob pattern."""
    dirs = [Path(p) for p in glob.glob(str(BASE_DIR / pattern)) if Path(p).is_dir()]
    return max(dirs, key=lambda d: d.name) if dirs else None


def load_json(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Read a JSON report, returning None if it is missing or unreadable."""
    if not path or not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not read report {path.name}: {exc}")
        return None


@app.route("/figures/<group>/<path:filename>")
def serve_figure(group: str, filename: str):
    """Serve a matplotlib/seaborn figure from the latest analysis or conservation run."""
    patterns = {"analysis": "reports/charts/*", "conservation": "reports/conservation/*"}
    if group not in patterns or not filename.endswith(".png"):
        return "Figure not found", 404
    run_dir = latest_run_dir(patterns[group])
    if not run_dir or not (run_dir / filename).exists():
        return "Figure not found", 404
    return send_from_directory(run_dir, filename)


def latest_reports() -> Dict[str, Any]:
    """Locate the newest ETL, analysis and conservation reports and their chart folders."""
    etl_path = get_latest_file("reports/etl_report_*.json")
    analysis_path = get_latest_file("reports/analysis_report_*.json")
    conservation_dir = latest_run_dir("reports/conservation/*")
    analysis = load_json(analysis_path)
    conservation = load_json(conservation_dir / "conservation_report.json" if conservation_dir else None)

    # GBIF results were computed against a set of hotspot cells; flag when the
    # current analysis ranks a different set of Medium/High cells.
    conservation_stale = False
    if analysis and conservation:
        current = {
            c["grid_id"] for c in analysis.get("top_hotspot_cells", [])
            if c.get("priority_label") in ("High Priority", "Medium Priority")
        }
        queried = {c["grid_id"] for c in conservation.get("cell_conservation_summaries", [])}
        conservation_stale = current != queried

    return {
        "etl_path": etl_path,
        "analysis_path": analysis_path,
        "etl": load_json(etl_path),
        "analysis": analysis,
        "conservation": conservation,
        "conservation_dir": conservation_dir,
        "charts_dir": latest_run_dir("reports/charts/*"),
        "conservation_stale": conservation_stale,
    }


@app.route("/api/dashboard")
def api_dashboard():
    """Return the latest ETL, EDA and GBIF results, read directly from generated reports."""
    r = latest_reports()
    charts_dir, conservation_dir = r["charts_dir"], r["conservation_dir"]
    figures = {
        "analysis": sorted(p.name for p in charts_dir.glob("*.png")) if charts_dir else [],
        "conservation": sorted(p.name for p in conservation_dir.glob("*.png")) if conservation_dir else [],
    }
    return jsonify({
        "etl": r["etl"],
        "analysis": r["analysis"],
        "conservation": r["conservation"],
        "conservation_stale": r["conservation_stale"],
        "figures": figures,
        "sources": {
            "etl": r["etl_path"].name if r["etl_path"] else None,
            "analysis": r["analysis_path"].name if r["analysis_path"] else None,
            "conservation": conservation_dir.name if conservation_dir else None,
        },
    })


PDF_KINDS = {
    "project": "Project Report",
    "etl": "ETL Report",
    "analysis": "Analysis Report",
    "biodiversity": "Biodiversity Report",
}


@app.route("/reports/<kind>.pdf")
def report_pdf(kind: str):
    """Build a PDF report from the latest JSON reports and serve it (inline, or ?download=1)."""
    from forestsentinel import pdf_report

    if kind not in PDF_KINDS:
        return "Unknown report", 404
    r = latest_reports()
    etl, analysis, cons = r["etl"], r["analysis"], r["conservation"]
    needed = {"etl": etl, "analysis": analysis, "biodiversity": cons, "project": analysis}[kind]
    if not needed:
        return f"No data for the {PDF_KINDS[kind].lower()} yet. Run the pipeline first.", 404

    out = BASE_DIR / "reports" / "pdf" / f"ForestSentinel_{PDF_KINDS[kind].replace(' ', '_')}.pdf"
    try:
        if kind == "etl":
            pdf_report.build_etl_pdf(etl, out)
        elif kind == "analysis":
            pdf_report.build_analysis_pdf(analysis, r["charts_dir"], out, etl=etl)
        elif kind == "biodiversity":
            pdf_report.build_conservation_pdf(cons, r["conservation_dir"], out)
        else:
            pdf_report.build_project_pdf(etl, analysis, r["charts_dir"], cons, r["conservation_dir"], out,
                                         cons_stale=r["conservation_stale"])
    except Exception as exc:
        logger.exception("PDF generation failed")
        return f"Could not build the PDF: {exc}", 500

    stamp = (analysis or etl or {}).get("generated_at") or (etl or {}).get("started_at") or ""
    download_name = f"ForestSentinel_{PDF_KINDS[kind].replace(' ', '_')}_{stamp[:10] or 'latest'}.pdf"
    return send_file(out, mimetype="application/pdf", as_attachment=request.args.get("download") == "1",
                     download_name=download_name, max_age=0)


@app.route("/api/metrics")
def api_metrics():
    """Return headline metrics from the latest reports (kept for API compatibility)."""
    analysis = load_json(get_latest_file("reports/analysis_report_*.json")) or {}
    etl = load_json(get_latest_file("reports/etl_report_*.json")) or {}
    grid = analysis.get("grid_metadata", {})
    overview = analysis.get("eda_results", {}).get("overview", {})
    return jsonify({
        "status": "ok" if analysis else "no_analysis",
        "database_project": etl.get("database_project") or etl.get("firebase_project_id"),
        "raw_rows_extracted": etl.get("counts", {}).get("raw_rows_extracted"),
        "fire_detections": overview.get("total_records"),
        "populated_grid_cells": grid.get("total_populated_cells"),
        "high_priority_hotspots": grid.get("high_priority_count"),
        "medium_priority_hotspots": grid.get("medium_priority_count"),
        "low_priority_hotspots": grid.get("low_priority_count"),
    })


@app.route("/api/run/<stage>", methods=["POST"])
def run_stage(stage: str):
    """Execute pipeline scripts directly from the localhost UI."""
    scripts = {
        "etl": "run_pipeline.py",
        "analysis": "run_analysis.py",
        "conservation": "run_conservation_analysis.py",
    }

    if stage not in scripts:
        return jsonify({"error": f"Invalid stage '{stage}'. Choose from {list(scripts.keys())}"}), 400

    script_path = BASE_DIR / scripts[stage]
    if not script_path.exists():
        return jsonify({"error": f"Script {scripts[stage]} not found."}), 404

    try:
        logger.info(f"Triggering {scripts[stage]} via web interface...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )

        output = result.stdout or result.stderr
        success = result.returncode == 0

        return jsonify({
            "success": success,
            "stage": stage,
            "script": scripts[stage],
            "returncode": result.returncode,
            "output": output[-1500:],  # return tail
            "map_updated": stage in ("analysis", "conservation") and success,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": f"{scripts[stage]} timed out after 180 seconds."}), 504
    except Exception as exc:
        logger.exception("Pipeline execution failed")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"================================================================")
    print(f" ForestSentinel Localhost Web Dashboard")
    print(f" URL: http://localhost:{port}")
    print(f" Press Ctrl+C to terminate.")
    print(f"================================================================")
    app.run(host="0.0.0.0", port=port, debug=False)
