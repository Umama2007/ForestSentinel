"""PDF report builder for ForestSentinel.

Turns the JSON reports written by each pipeline stage (ETL, analysis, conservation)
into designed, printable PDF reports: a dark cover page with the headline figures,
then white content pages with tables, auto-written findings and the generated charts.

All builders read only the JSON payloads and chart PNGs, so a PDF can be rebuilt
at any time from an existing run without touching Supabase or the APIs.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4
MARGIN_X = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X

# Palette: dark cover, white body; accents match the web dashboard.
INK = colors.HexColor("#0f0f12")
INK_2 = colors.HexColor("#52525b")
INK_3 = colors.HexColor("#8a8a93")
LINE = colors.HexColor("#e7e7ea")
SOFT = colors.HexColor("#f6f6f8")
COVER_BG = colors.HexColor("#05070d")
PANEL_BG = colors.HexColor("#080e1b")
VIOLET = colors.HexColor("#059669")
PINK = colors.HexColor("#d97706")
BLUE = colors.HexColor("#0891b2")
HIGH = colors.HexColor("#dc2626")
MEDIUM = colors.HexColor("#d97706")
LOW = colors.HexColor("#64748b")
GOOD = colors.HexColor("#16a34a")
WARN_BG = colors.HexColor("#fff7e6")
WARN_INK = colors.HexColor("#8a5a00")
GRADIENT = [colors.HexColor("#34d399"), colors.HexColor("#22d3ee"), colors.HexColor("#fbbf24")]

PRIORITY_COLORS = {"High Priority": HIGH, "Medium Priority": MEDIUM, "Low Priority": LOW}

LIMITATIONS = [
    "NASA FIRMS records thermal anomalies seen by satellite. A detection is not ground-verified and may be an "
    "agricultural burn, a wildfire or another heat source.",
    "Near-real-time data covers a short window (a few days) and cannot establish long-term trends.",
    "The Fire Activity Priority Score is a retrospective ranking of past detections. It is not a fire prediction "
    "model and not an emergency warning.",
    "GBIF records show documented past occurrences of animals, not confirmed current presence or harm.",
    "Wildlife data is aggregated to 0.25° grid cells; exact animal coordinates are never stored or shown.",
]


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

def _register_fonts() -> Tuple[str, str, str, str]:
    """Register a TTF family (Segoe UI on Windows, DejaVu from matplotlib elsewhere).

    Returns:
        (regular, bold, semibold, mono) font names.
    """
    if "FS-Regular" in pdfmetrics.getRegisteredFontNames():
        return "FS-Regular", "FS-Bold", "FS-Semibold", "FS-Mono"

    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    try:
        import matplotlib
        mpl = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
    except Exception:  # pragma: no cover - matplotlib is a hard dependency
        mpl = Path(".")

    candidates = {
        "FS-Regular": [win / "segoeui.ttf", mpl / "DejaVuSans.ttf"],
        "FS-Bold": [win / "segoeuib.ttf", mpl / "DejaVuSans-Bold.ttf"],
        "FS-Semibold": [win / "seguisb.ttf", win / "segoeuib.ttf", mpl / "DejaVuSans-Bold.ttf"],
        "FS-Mono": [win / "consola.ttf", mpl / "DejaVuSansMono.ttf"],
    }
    resolved = {}
    for name, paths in candidates.items():
        for path in paths:
            if path.exists():
                pdfmetrics.registerFont(TTFont(name, str(path)))
                resolved[name] = name
                break
        else:
            resolved[name] = {"FS-Mono": "Courier", "FS-Regular": "Helvetica"}.get(name, "Helvetica-Bold")
    return resolved["FS-Regular"], resolved["FS-Bold"], resolved["FS-Semibold"], resolved["FS-Mono"]


REGULAR, BOLD, SEMIBOLD, MONO = _register_fonts()


def _style(name: str, **kw: Any) -> ParagraphStyle:
    base = dict(fontName=REGULAR, fontSize=9.5, leading=14, textColor=INK_2)
    base.update(kw)
    return ParagraphStyle(name, **base)


S_BODY = _style("body")
S_SMALL = _style("small", fontSize=8, leading=11, textColor=INK_3)
S_EYEBROW = _style("eyebrow", fontName=SEMIBOLD, fontSize=8, leading=10, textColor=VIOLET)
S_H1 = _style("h1", fontName=BOLD, fontSize=22, leading=26, textColor=INK, spaceAfter=4)
S_H2 = _style("h2", fontName=SEMIBOLD, fontSize=12, leading=16, textColor=INK, spaceBefore=6, spaceAfter=4)
S_CELL = _style("cell", fontSize=8.5, leading=11, textColor=INK)
S_CELL_MUTED = _style("cellm", fontSize=8, leading=10.5, textColor=INK_3)
S_CELL_R = _style("cellr", fontSize=8.5, leading=11, textColor=INK, alignment=TA_RIGHT)
S_HEAD = _style("head", fontName=SEMIBOLD, fontSize=7.5, leading=10, textColor=INK_3)
S_HEAD_R = _style("headr", fontName=SEMIBOLD, fontSize=7.5, leading=10, textColor=INK_3, alignment=TA_RIGHT)
S_METRIC = _style("metric", fontName=BOLD, fontSize=20, leading=23, textColor=INK)
S_METRIC_LABEL = _style("metricl", fontSize=8, leading=10, textColor=INK_2)
S_CAPTION = _style("caption", fontSize=8, leading=11, textColor=INK_3, spaceBefore=4)
S_FINDING = _style("finding", fontSize=9.5, leading=14, textColor=INK, leftIndent=10, bulletIndent=0)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(value: Any, dec: int = 0) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{dec}f}"
    except (TypeError, ValueError):
        return str(value)


def _pct(part: float, whole: float) -> float:
    return (part / whole * 100.0) if whole else 0.0


def _day(iso: Optional[str], with_year: bool = False) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    return dt.strftime("%d %b %Y" if with_year else "%d %b").lstrip("0")


def _datetime(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    return dt.strftime("%d %b %Y, %H:%M UTC").lstrip("0")


def _cell_name(grid_id: str) -> str:
    try:
        _, lat, lon = grid_id.split("_")
        lat_f, lon_f = float(lat), float(lon)
    except ValueError:
        return grid_id
    return f"{abs(lat_f):.2f}°{'S' if lat_f < 0 else 'N'}, {abs(lon_f):.2f}°{'W' if lon_f < 0 else 'E'}"


def _esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Flowables
# ---------------------------------------------------------------------------

class Bar(Flowable):
    """Inline horizontal bar used inside table cells (record flow, scores)."""

    def __init__(self, fraction: float, color: colors.Color, width: float = 60 * mm, height: float = 5) -> None:
        super().__init__()
        self.fraction = max(0.0, min(1.0, fraction))
        self.color = color
        self.width = width
        self.height = height

    def wrap(self, *_: Any) -> Tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(SOFT)
        c.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        if self.fraction > 0:
            c.setFillColor(self.color)
            c.roundRect(0, 0, max(self.height, self.width * self.fraction), self.height, self.height / 2, stroke=0, fill=1)


class GradientRule(Flowable):
    """Thin violet-pink-blue rule, the report's signature accent."""

    def __init__(self, width: float = 28 * mm, height: float = 2.2) -> None:
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, *_: Any) -> Tuple[float, float]:
        return self.width, self.height

    def draw(self) -> None:
        _gradient_bar(self.canv, 0, 0, self.width, self.height)


def _lerp(a: colors.Color, b: colors.Color, t: float) -> colors.Color:
    return colors.Color(a.red + (b.red - a.red) * t, a.green + (b.green - a.green) * t, a.blue + (b.blue - a.blue) * t)


def _gradient_bar(c: Any, x: float, y: float, w: float, h: float, steps: int = 120) -> None:
    seg = w / steps
    for i in range(steps):
        t = i / (steps - 1)
        col = _lerp(GRADIENT[0], GRADIENT[1], t * 2) if t < 0.5 else _lerp(GRADIENT[1], GRADIENT[2], (t - 0.5) * 2)
        c.setFillColor(col)
        c.rect(x + i * seg, y, seg + 0.4, h, stroke=0, fill=1)


def _section(num: str, title: str, intro: str = "") -> List[Flowable]:
    """Section opener: number eyebrow, title, accent rule, optional intro."""
    block: List[Flowable] = [
        CondPageBreak(70 * mm),
        Spacer(1, 6 * mm),
        Paragraph(f"{num}", S_EYEBROW),
        Spacer(1, 2),
        Paragraph(_esc(title), S_H1),
        GradientRule(),
        Spacer(1, 4 * mm),
    ]
    if intro:
        block += [Paragraph(intro, S_BODY), Spacer(1, 4 * mm)]
    return block


def _metrics(items: Sequence[Tuple[str, str, str]]) -> Table:
    """Row of metric tiles: (label, value, sub)."""
    cells = [[
        [Paragraph(_esc(label), S_METRIC_LABEL), Spacer(1, 3), Paragraph(value, S_METRIC), Paragraph(_esc(sub), S_SMALL)]
        for label, value, sub in items
    ]]
    gap = 3 * mm
    col_w = (CONTENT_W - gap * (len(items) - 1)) / len(items)
    widths: List[float] = []
    row: List[Any] = []
    for i, cell in enumerate(cells[0]):
        if i:
            widths.append(gap)
            row.append("")
        widths.append(col_w)
        row.append(cell)
    t = Table([row], colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]
    for i in range(0, len(row), 2):
        style += [
            ("BACKGROUND", (i, 0), (i, 0), SOFT),
            ("LEFTPADDING", (i, 0), (i, 0), 10),
            ("RIGHTPADDING", (i, 0), (i, 0), 8),
        ]
    t.setStyle(TableStyle(style))
    return t


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]], widths: Sequence[float],
           numeric: Sequence[int] = ()) -> Table:
    """Zebra table; ``numeric`` column indexes are right-aligned."""
    head = [Paragraph(_esc(h), S_HEAD_R if i in numeric else S_HEAD) for i, h in enumerate(headers)]
    body = []
    for r in rows:
        body.append([
            c if isinstance(c, Flowable) else Paragraph(str(c), S_CELL_R if i in numeric else S_CELL)
            for i, c in enumerate(r)
        ])
    t = Table([head] + body, colWidths=widths, repeatRows=1)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(body) + 1):
        style.append(("LINEBELOW", (0, i), (-1, i), 0.4, LINE))
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafafb")))
    t.setStyle(TableStyle(style))
    return t


def _figure(path: Optional[Path], caption: str, width: float = CONTENT_W) -> List[Flowable]:
    """Chart PNG inside a dark rounded panel (the charts use the dark dashboard theme)."""
    parts = _figure_parts(path, caption, width)
    return [KeepTogether(parts), Spacer(1, 5 * mm)] if parts else []


def _figure_parts(path: Optional[Path], caption: str, width: float) -> List[Flowable]:
    """Panel + caption, unwrapped so it can also sit inside a table cell."""
    if not path or not Path(path).exists():
        return []
    iw, ih = ImageReader(str(path)).getSize()
    pad = 6
    img_w = width - 2 * pad
    img = Image(str(path), width=img_w, height=img_w * ih / iw)
    panel = Table([[img]], colWidths=[width], cornerRadii=[6, 6, 6, 6])
    panel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]))
    return [panel, Paragraph(caption, S_CAPTION)]


def _figure_pair(left: Tuple[Optional[Path], str], right: Tuple[Optional[Path], str]) -> List[Flowable]:
    """Two charts side by side."""
    gap = 4 * mm
    w = (CONTENT_W - gap) / 2
    lf, rf = _figure_parts(left[0], left[1], w), _figure_parts(right[0], right[1], w)
    if not lf or not rf:
        return _figure(*left) + _figure(*right)
    t = Table([[lf, "", rf]], colWidths=[w, gap, w])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return [t, Spacer(1, 5 * mm)]


def _findings(lines: Iterable[str]) -> List[Flowable]:
    return [Paragraph(line, S_FINDING, bulletText="•") for line in lines if line] + [Spacer(1, 3 * mm)]


def _callout(text: str, warn: bool = False) -> Table:
    t = Table([[Paragraph(text, _style("call", fontSize=8.5, leading=12, textColor=WARN_INK if warn else INK_2))]],
              colWidths=[CONTENT_W], cornerRadii=[5, 5, 5, 5])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WARN_BG if warn else SOFT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

class _ReportDoc(BaseDocTemplate):
    """Two templates: a dark full-bleed cover and white body pages with header/footer."""

    def __init__(self, path: Path, label: str, cover: Dict[str, Any]) -> None:
        super().__init__(
            str(path), pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
            topMargin=22 * mm, bottomMargin=18 * mm,
            title=f"ForestSentinel — {label}", author="ForestSentinel", subject=cover.get("title", label),
        )
        self.label = label
        self.cover = cover
        self.generated = datetime.now(timezone.utc)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body", showBoundary=0)
        cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id="cover", showBoundary=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame], onPage=self._draw_cover),
            PageTemplate(id="body", frames=[frame], onPage=self._draw_body),
        ])

    def _draw_cover(self, c: Any, _doc: Any) -> None:
        cv = self.cover
        c.saveState()
        c.setFillColor(COVER_BG)
        c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        # soft glow
        for r, a in ((240, 0.035), (170, 0.04), (100, 0.045)):
            c.setFillColor(colors.Color(0.49, 0.23, 0.93, alpha=a))
            c.circle(PAGE_W * 0.85, PAGE_H * 0.86, r, stroke=0, fill=1)
        _gradient_bar(c, 0, PAGE_H - 4, PAGE_W, 4)

        x = MARGIN_X + 4 * mm
        # wordmark
        y = PAGE_H - 30 * mm
        _gradient_bar(c, x, y - 1, 13, 13, steps=13)
        c.setFillColor(COVER_BG)
        c.roundRect(x + 3.5, y + 2.5, 6, 6, 1.5, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(BOLD, 12)
        c.drawString(x + 20, y + 1.5, "ForestSentinel")

        # eyebrow + title
        y = PAGE_H * 0.62
        c.setFillColor(colors.HexColor("#34d399"))
        c.setFont(SEMIBOLD, 9)
        c.drawString(x, y + 46 * mm, cv.get("eyebrow", self.label).upper())
        c.setFillColor(colors.white)
        c.setFont(BOLD, 34)
        ty = y + 32 * mm
        for line in cv.get("title_lines", [self.label]):
            c.drawString(x, ty, line)
            ty -= 40
        c.setFillColor(colors.HexColor("#a1a1aa"))
        c.setFont(REGULAR, 11)
        sy = ty - 4
        for line in cv.get("subtitle_lines", []):
            c.drawString(x, sy, line)
            sy -= 16

        # metrics row
        metrics = cv.get("metrics", [])[:4]
        if metrics:
            my = PAGE_H * 0.36
            col = (PAGE_W - 2 * x) / len(metrics)
            for i, (value, label) in enumerate(metrics):
                mx = x + i * col
                c.setStrokeColor(colors.HexColor("#27272a"))
                c.setLineWidth(0.8)
                c.line(mx, my + 34, mx + col - 8 * mm, my + 34)
                c.setFillColor(colors.white)
                c.setFont(BOLD, 26)
                c.drawString(mx, my, str(value))
                c.setFillColor(colors.HexColor("#a1a1aa"))
                c.setFont(REGULAR, 8.5)
                c.drawString(mx, my - 14, str(label))

        # details
        dy = PAGE_H * 0.22
        c.setFont(REGULAR, 8.5)
        for key, value in cv.get("details", []):
            c.setFillColor(colors.HexColor("#71717a"))
            c.drawString(x, dy, key)
            c.setFillColor(colors.HexColor("#e4e4e7"))
            c.drawString(x + 42 * mm, dy, str(value))
            dy -= 14

        c.setFillColor(colors.HexColor("#52525b"))
        c.setFont(REGULAR, 7.5)
        c.drawString(x, 16 * mm, "Retrospective analysis of NASA FIRMS satellite detections — not a fire prediction model.")
        c.drawRightString(PAGE_W - x, 16 * mm, f"Generated {self.generated.strftime('%d %b %Y, %H:%M UTC').lstrip('0')}")
        c.restoreState()

    def _draw_body(self, c: Any, doc: Any) -> None:
        c.saveState()
        _gradient_bar(c, 0, PAGE_H - 3, PAGE_W, 3)
        top = PAGE_H - 12 * mm
        c.setFont(BOLD, 8.5)
        c.setFillColor(INK)
        c.drawString(MARGIN_X, top, "ForestSentinel")
        c.setFont(REGULAR, 8.5)
        c.setFillColor(INK_3)
        c.drawString(MARGIN_X + pdfmetrics.stringWidth("ForestSentinel  ", BOLD, 8.5), top, self.label)
        c.drawRightString(PAGE_W - MARGIN_X, top, self.cover.get("header_right", ""))
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(MARGIN_X, top - 5, PAGE_W - MARGIN_X, top - 5)

        c.setFont(REGULAR, 7.5)
        c.setFillColor(INK_3)
        c.drawString(MARGIN_X, 10 * mm, "Retrospective analysis — not a fire prediction model or emergency warning.")
        c.drawRightString(PAGE_W - MARGIN_X, 10 * mm, f"{doc.page - 1}")
        c.restoreState()


def _build(path: Path, label: str, cover: Dict[str, Any], story: List[Flowable]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _ReportDoc(path, label, cover)
    doc.build([NextPageTemplate("body"), PageBreak()] + story)
    logger.info("Saved PDF report: %s", path)
    return path


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _sec_etl(etl: Dict[str, Any], num: str = "01") -> List[Flowable]:
    c = etl.get("counts", {})
    raw = c.get("raw_rows_extracted", 0) or 0
    rejected = (c.get("cleaning_rejections", 0) or 0) + (c.get("pydantic_rejections", 0) or 0)
    story = _section(num, "Data quality: ETL run",
                     "Every record from the FIRMS pull, traced from extraction to Supabase. Records that fail "
                     "cleaning or Pydantic validation are written to a separate <font name='%s'>rejected_records</font> "
                     "collection rather than silently dropped." % MONO)
    story += [_metrics([
        ("Extracted", _fmt(raw), "raw rows from the FIRMS API"),
        ("Valid", _fmt(c.get("valid_records")), f"{_fmt(_pct(c.get('valid_records', 0), raw), 1)}% pass rate"),
        ("Inserted", _fmt(c.get("inserted_records")), "new detection keys"),
        ("Rejected", _fmt(rejected), "cleaning + schema"),
    ]), Spacer(1, 5 * mm)]

    flow = [
        ("Extracted from FIRMS", "raw API rows", c.get("raw_rows_extracted"), INK_2),
        ("Exact duplicates removed", "pandas drop_duplicates", c.get("exact_duplicates_removed"), HIGH),
        ("Rejected during cleaning", "bad coordinates or timestamps", c.get("cleaning_rejections"), HIGH),
        ("Rejected by Pydantic", "schema validation", c.get("pydantic_rejections"), HIGH),
        ("Valid records", "passed every check", c.get("valid_records"), VIOLET),
        ("Inserted into Supabase", "new SHA-256 detection keys", c.get("inserted_records"), VIOLET),
        ("Skipped, already stored", "same key from an earlier run", c.get("skipped_existing_records"), LOW),
        ("Rejections saved", "rejected_records collection", c.get("saved_rejections"), HIGH),
    ]
    rows = [[
        Paragraph(f"{label}<br/><font size=7.5 color='#8a8a93'>{sub}</font>", S_CELL),
        Bar(_pct(v or 0, raw) / 100, color, width=78 * mm),
        _fmt(v),
    ] for label, sub, v, color in flow]
    story += [Paragraph("Record flow", S_H2), _table(["Stage", "", "Records"], rows, [62 * mm, 86 * mm, 26 * mm], numeric=[2]),
              Spacer(1, 5 * mm)]

    skipped = c.get("skipped_existing_records", 0) or 0
    story += [Paragraph("What happened", S_H2)] + _findings([
        f"The FIRMS API returned <b>{_fmt(raw)}</b> detections for the {etl.get('day_range', '—')}-day window over "
        f"bounding box {_esc(etl.get('study_bbox', '—'))}.",
        f"<b>{_fmt(c.get('valid_records'))}</b> records passed cleaning and Pydantic validation "
        f"({_fmt(_pct(c.get('valid_records', 0), raw), 1)}%); {_fmt(rejected)} were rejected.",
        f"<b>{_fmt(c.get('inserted_records'))}</b> were new and inserted into Supabase. {_fmt(skipped)} already existed "
        "from an earlier run and were skipped, because each record's SHA-256 key is deterministic — rerunning the "
        "pipeline never creates duplicates." if skipped else
        f"<b>{_fmt(c.get('inserted_records'))}</b> were inserted into Supabase under deterministic SHA-256 keys.",
    ])

    details = [
        ("Run ID", etl.get("run_id")), ("Status", str(etl.get("status", "—")).capitalize()),
        ("Source", etl.get("api_source")), ("Bounding box", etl.get("study_bbox")),
        ("Day range", etl.get("day_range")), ("Started", _datetime(etl.get("started_at"))),
        ("Duration", f"{_fmt(etl.get('duration_seconds'), 1)} s"), ("Database project", etl.get("database_project") or etl.get("firebase_project_id")),
        ("Raw CSV archive", Path(str(etl.get("raw_csv_saved_at", "—"))).name),
    ]
    story += [Paragraph("Run details", S_H2),
              _table(["Field", "Value"], [[k, f"<font name='{MONO}' size=8>{_esc(v)}</font>"] for k, v in details],
                     [45 * mm, CONTENT_W - 45 * mm])]

    sample = etl.get("rejected_sample") or []
    if sample:
        story += [Spacer(1, 4 * mm), Paragraph("Sample of rejected records", S_H2),
                  _table(["Reason", "Record"], [[_esc(r.get("reason", r.get("error", "—"))), _esc(str(r)[:140])] for r in sample],
                         [55 * mm, CONTENT_W - 55 * mm])]
    return story


def _sec_overview(a: Dict[str, Any], num: str) -> List[Flowable]:
    eda = a.get("eda_results", {})
    ov = eda.get("overview", {})
    grid = a.get("grid_metadata", {})
    dates = ov.get("unique_detection_dates") or []
    story = _section(num, "Study window & dataset",
                     "Validated detections read back from Supabase and restricted to the FIRMS query window.")
    story += [_metrics([
        ("Detections analysed", _fmt(ov.get("total_records")), f"{len(dates)} observation days"),
        ("Window", f"{_day(dates[0]) if dates else '—'} – {_day(dates[-1]) if dates else '—'}", "UTC dates"),
        ("Grid cells", _fmt(grid.get("total_populated_cells")), f"{grid.get('grid_size_degrees', 0.25)}° populated cells"),
        ("High priority", _fmt(grid.get("high_priority_count")), "cells scoring ≥ 70"),
    ]), Spacer(1, 5 * mm)]

    total = ov.get("total_records") or 0
    rows = [
        ["Satellite / instrument", f"{', '.join(ov.get('satellites', []))} / {', '.join(ov.get('instruments', []))}"],
        ["First detection", _datetime(ov.get("earliest_detection_datetime"))],
        ["Last detection", _datetime(ov.get("latest_detection_datetime"))],
        ["Day / night passes", f"{_fmt(ov.get('day_detections'))} day · {_fmt(ov.get('night_detections'))} night"],
        ["Records with FRP", f"{_fmt(ov.get('records_with_frp_count'))} ({_fmt(ov.get('records_with_frp_percentage'), 1)}%)"],
    ]
    missing = eda.get("distributions", {}).get("missing_values", {})
    if missing:
        rows.append(["Missing values", ", ".join(f"{k}: {v}" for k, v in missing.items()) if any(missing.values())
                     else f"None — all {len(missing)} key fields complete for {_fmt(total)} records"])
    story += [_table(["Property", "Value"], rows, [45 * mm, CONTENT_W - 45 * mm]), Spacer(1, 4 * mm)]
    notes = eda.get("data_quality_notes") or []
    if notes:
        story += [Paragraph("Data quality notes", S_H2)] + _findings(_esc(n) for n in notes)
    return story


def _sec_distributions(a: Dict[str, Any], charts: Optional[Path], num: str) -> List[Flowable]:
    eda = a.get("eda_results", {})
    dist = eda.get("distributions", {})
    story = _section(num, "Distributions & outliers",
                     "Fire Radiative Power (FRP) measures how much energy a fire releases; brightness temperatures "
                     "come from the VIIRS I-4 (3.7 µm) fire channel and I-5 (11 µm) background channel. Outliers are "
                     "values beyond Tukey's fences: Q1 − 1.5·IQR or Q3 + 1.5·IQR.")
    metrics = [k for k in ("frp", "bright_ti4", "bright_ti5") if dist.get(k, {}).get("available")]
    if metrics:
        rows = []
        for k in metrics:
            d = dist[k]
            rows.append([d["label"], _fmt(d["median"], 1), _fmt(d["mean"], 1), _fmt(d["iqr"], 1),
                         f"{_fmt(d['lower_fence'], 1)} – {_fmt(d['upper_fence'], 1)}", _fmt(d["skewness"], 2),
                         f"<b>{_fmt(d['outlier_count'])}</b> ({_fmt(d['outlier_percentage'], 1)}%)"])
        story += [_table(["Metric", "Median", "Mean", "IQR", "Fences", "Skew", "Outliers"], rows,
                         [50 * mm, 17 * mm, 17 * mm, 15 * mm, 30 * mm, 15 * mm, 30 * mm], numeric=[1, 2, 3, 4, 5, 6]),
                  Spacer(1, 4 * mm)]
        frp = dist.get("frp", {})
        t4 = dist.get("bright_ti4", {})
        fdn = dist.get("frp_by_daynight", {})
        lines = []
        if frp.get("available"):
            lines.append(
                f"FRP is strongly right-skewed (skew {_fmt(frp['skewness'], 2)}): most fires are small "
                f"(median {_fmt(frp['median'], 1)} MW) while <b>{_fmt(frp['outlier_count'])}</b> detections "
                f"({_fmt(frp['outlier_percentage'], 1)}%) exceed the upper fence of {_fmt(frp['upper_fence'], 1)} MW, "
                f"up to {_fmt(frp['max'], 0)} MW. The mean ({_fmt(frp['mean'], 1)} MW) is pulled up by these few intense fires.")
        if t4.get("available"):
            lines.append(
                f"I-4 brightness is left-skewed (skew {_fmt(t4['skewness'], 2)}); its {_fmt(t4['outlier_count'])} outliers "
                f"sit below {_fmt(t4['lower_fence'], 1)} K — cooler, mostly night-time detections rather than extreme fires.")
        if fdn.get("D") and fdn.get("N"):
            lines.append(
                f"Daytime detections are far more intense: median FRP {_fmt(fdn['D']['median'], 1)} MW by day versus "
                f"{_fmt(fdn['N']['median'], 1)} MW at night.")
        story += [Paragraph("Findings", S_H2)] + _findings(lines)

    if charts:
        story += _figure(charts / "frp_distribution.png", "Figure — FRP histogram with KDE, mean and median.")
        story += _figure(charts / "brightness_distribution.png", "Figure — I-4 and I-5 brightness temperature histograms.")
        story += _figure(charts / "outlier_boxplots.png", "Figure — Box plots with Tukey 1.5·IQR whiskers; dots are outliers.")

    conf = eda.get("sensors", {}).get("confidence_counts") or eda.get("overview", {}).get("confidence_counts", {})
    if conf:
        total = sum(conf.values())
        names = {"h": "High", "n": "Nominal", "l": "Low"}
        rows = [[names.get(k, k), Bar(_pct(conf[k], total) / 100, VIOLET, width=80 * mm), _fmt(conf[k]),
                 f"{_fmt(_pct(conf[k], total), 1)}%"] for k in ("h", "n", "l") if k in conf]
        story += [Paragraph("Detection confidence", S_H2),
                  _table(["Class", "", "Count", "Share"], rows, [35 * mm, 88 * mm, 25 * mm, 26 * mm], numeric=[2, 3]),
                  Spacer(1, 4 * mm)]
    return story


def _sec_timing(a: Dict[str, Any], charts: Optional[Path], num: str) -> List[Flowable]:
    t = a.get("eda_results", {}).get("temporal", {})
    daily = t.get("daily_detections", {})
    total = sum(daily.values()) or 1
    peak = max(daily.items(), key=lambda kv: kv[1]) if daily else None
    story = _section(num, "When fires are detected",
                     "Detections per day and per hour (UTC), and how day and night satellite passes differ.")
    rows = [[_day(d + "T00:00:00", True), Bar(v / max(daily.values()), PINK, width=90 * mm), _fmt(v),
             f"{_fmt(_pct(v, total), 1)}%"] for d, v in sorted(daily.items())]
    story += [_table(["Date", "", "Detections", "Share"], rows, [32 * mm, 96 * mm, 24 * mm, 22 * mm], numeric=[2, 3]),
              Spacer(1, 4 * mm)]

    dn = t.get("day_night_distribution", {})
    day, night = dn.get("D", 0), dn.get("N", 0)
    hourly = t.get("hourly_detections", {})
    busiest = sorted(((int(h), v) for h, v in hourly.items() if v), key=lambda x: -x[1])[:2]
    lines = [
        f"Peak day: <b>{_day(peak[0] + 'T00:00:00', True)}</b> with {_fmt(peak[1])} detections "
        f"({_fmt(_pct(peak[1], total), 1)}% of the window)." if peak else "",
        _esc(t.get("trend_explanation", "")),
        f"<b>{_fmt(_pct(day, day + night), 1)}%</b> of detections come from daytime passes ({_fmt(day)}) and "
        f"{_fmt(_pct(night, day + night), 1)}% from night passes ({_fmt(night)}).",
        ("Detections cluster at " + " and ".join(f"{h:02d}:00 UTC ({(h - 4) % 24:02d}:00 local)" for h, _ in busiest) +
         " — the VIIRS NOAA-21 overpass times, not the times fires start.") if busiest else "",
    ]
    story += [Paragraph("Findings", S_H2)] + _findings(lines)
    if charts:
        story += _figure(charts / "daily_fire_activity.png", "Figure — Detections per day.")
        story += _figure_pair((charts / "hourly_activity.png", "Figure — Detections per UTC hour, day vs night passes."),
                              (charts / "day_night_distribution.png", "Figure — Day vs night share."))
    return story


def _sec_hotspots(a: Dict[str, Any], charts: Optional[Path], num: str) -> List[Flowable]:
    grid = a.get("grid_metadata", {})
    cells = a.get("top_hotspot_cells", [])
    story = _section(num, "Hotspot ranking",
                     f"The study area is divided into {grid.get('grid_size_degrees', 0.25)}° grid cells (~27 km). Each "
                     "populated cell receives an explainable 0–100 Fire Activity Priority Score from four min-max "
                     "normalised components, then a High / Medium / Low label.")
    total = grid.get("total_populated_cells") or 0
    story += [_metrics([
        ("High priority", _fmt(grid.get("high_priority_count")), "score ≥ 70"),
        ("Medium priority", _fmt(grid.get("medium_priority_count")), "score 35 – 69.9"),
        ("Low priority", _fmt(grid.get("low_priority_count")), "score < 35"),
        ("Populated cells", _fmt(total), "with ≥ 1 detection"),
    ]), Spacer(1, 5 * mm)]

    names = {"frequency": "Detection frequency", "recency": "Recent activity (last 48 h)",
             "frp": "Mean FRP (intensity)", "confidence": "High / nominal confidence share"}
    weights = sorted((grid.get("active_weights") or {}).items(), key=lambda kv: -kv[1])
    story += [Paragraph("Score weights", S_H2),
              _table(["Component", "", "Weight"], [[names.get(k, k), Bar(w, VIOLET, width=90 * mm), f"{_fmt(w * 100)}%"]
                                                  for k, w in weights], [60 * mm, 94 * mm, 20 * mm], numeric=[2]),
              Spacer(1, 5 * mm)]

    rows = []
    for c in cells:
        label = c.get("priority_label", "")
        col = PRIORITY_COLORS.get(label, LOW)
        rows.append([
            str(c.get("rank")),
            Paragraph(f"{_cell_name(c['grid_id'])}<br/><font size=7 color='#8a8a93'>{c['grid_id']}</font>", S_CELL),
            Paragraph(f"<font color='{col.hexval().replace('0x', '#')}'>●</font> {label.replace(' Priority', '')}", S_CELL),
            Bar(c.get("priority_score", 0) / 100, col, width=26 * mm),
            _fmt(c.get("priority_score"), 1), _fmt(c.get("detection_count")), _fmt(c.get("recent_count")),
            _fmt(c.get("mean_frp"), 1),
        ])
    story += [Paragraph(f"Top {len(cells)} grid cells", S_H2),
              _table(["#", "Grid cell", "Priority", "", "Score", "Detections", "48 h", "Mean FRP"], rows,
                     [8 * mm, 40 * mm, 22 * mm, 30 * mm, 16 * mm, 21 * mm, 15 * mm, 22 * mm], numeric=[0, 4, 5, 6, 7]),
              Spacer(1, 4 * mm)]
    if cells:
        top = cells[0]
        story += [Paragraph("Findings", S_H2)] + _findings([
            f"The top cell, <b>{_cell_name(top['grid_id'])}</b>, scores {_fmt(top['priority_score'], 1)} with "
            f"{_fmt(top['detection_count'])} detections, {_fmt(top['recent_count'])} of them in the last 48 hours.",
            f"Only {_fmt(grid.get('high_priority_count'))} of {_fmt(total)} cells "
            f"({_fmt(_pct(grid.get('high_priority_count', 0), total), 1)}%) are High priority — fire activity is "
            "concentrated in a few places rather than spread evenly.",
        ])
    if charts:
        story += _figure(charts / "hotspot_priority_distribution.png", "Figure — Cells per priority class and top-ranked cells.")
        map_path = charts / "fire_activity_map.html"
        if map_path.exists():
            story += [_callout(f"The interactive Folium map for this run is saved at "
                               f"<font name='{MONO}' size=7.5>{_esc(map_path)}</font> and is embedded in the web dashboard.")]
    return story


def _sec_biodiversity(cons: Dict[str, Any], charts: Optional[Path], num: str, stale: bool = False) -> List[Flowable]:
    s = cons.get("summary_metrics", {})
    meta = cons.get("metadata", {})
    story = _section(num, "Fire and biodiversity",
                     "GBIF animal occurrence records were requested for every Medium and High fire-priority cell and "
                     "aggregated to the same 0.25° grid. Exact wildlife coordinates are never stored or shown.")
    if stale:
        story += [_callout("These GBIF results were computed for an earlier hotspot ranking. Re-run the biodiversity "
                           "stage (python run_conservation_analysis.py) to match the current priority cells.", warn=True),
                  Spacer(1, 4 * mm)]
    story += [_metrics([
        ("Cells queried", _fmt(s.get("priority_cells_considered")), "Medium + High fire cells"),
        ("GBIF records", _fmt(s.get("gbif_occurrence_records_received")), "animal occurrences"),
        ("Unique species", _fmt(s.get("unique_animal_species_found")), "deduplicated by taxon key"),
        ("IUCN verified", _fmt(s.get("species_with_verified_iucn_status")),
         "token configured" if meta.get("iucn_api_configured") else "IUCN token not configured"),
    ]), Spacer(1, 5 * mm)]

    cells = cons.get("cell_conservation_summaries", [])
    max_sp = max([c.get("total_species_recorded", 0) for c in cells] + [1])
    rows = [[
        Paragraph(f"{_cell_name(c['grid_id'])}<br/><font size=7 color='#8a8a93'>{c['grid_id']}</font>", S_CELL),
        c.get("fire_priority_label", "").replace(" Priority", ""),
        _fmt(c.get("fire_priority_score"), 1),
        _fmt(c.get("detection_count")),
        Bar(c.get("total_species_recorded", 0) / max_sp, BLUE, width=34 * mm),
        _fmt(c.get("total_species_recorded")),
        _esc(c.get("conservation_priority_label", "")),
    ] for c in cells]
    story += [_table(["Grid cell", "Fire priority", "Score", "Detections", "", "Species", "IUCN status"], rows,
                     [38 * mm, 21 * mm, 14 * mm, 19 * mm, 37 * mm, 15 * mm, 30 * mm], numeric=[2, 3, 5]),
              Spacer(1, 4 * mm)]
    if cells:
        richest = max(cells, key=lambda c: c.get("total_species_recorded", 0))
        story += [Paragraph("Findings", S_H2)] + _findings([
            f"<b>{_cell_name(richest['grid_id'])}</b> ({richest.get('fire_priority_label', '')}) has the most recorded animal "
            f"species: {_fmt(richest.get('total_species_recorded'))}.",
            f"{_fmt(s.get('gbif_occurrence_records_received'))} GBIF records resolved to "
            f"{_fmt(s.get('unique_animal_species_found'))} unique species across {_fmt(len(cells))} priority cells.",
            "Threat levels are reported only when verified through the IUCN Red List API; unverified species are "
            "labelled 'Pending IUCN Verification' and never guessed.",
        ])
    if charts:
        story += _figure(charts / "species_exposure_by_priority_zone.png", "Figure — Species recorded by fire-priority zone.")
        story += _figure(charts / "top_conservation_priority_cells.png", "Figure — Priority cells: fire score vs conservation exposure.")
    return story


def _sec_limitations(num: str) -> List[Flowable]:
    return _section(num, "Limitations & responsible use") + _findings(_esc(x) for x in LIMITATIONS)


def _cover_details(etl: Optional[Dict[str, Any]], extra: Sequence[Tuple[str, Any]] = ()) -> List[Tuple[str, Any]]:
    details: List[Tuple[str, Any]] = list(extra)
    if etl:
        details += [("Data source", f"NASA FIRMS · {etl.get('api_source', '—')}"),
                    ("Bounding box", etl.get("study_bbox", "—")),
                    ("Storage", f"Supabase · {etl.get('database_project') or etl.get('firebase_project_id') or '—'}")]
    return details


def _window_text(a: Dict[str, Any]) -> str:
    dates = a.get("eda_results", {}).get("overview", {}).get("unique_detection_dates") or []
    return f"{_day(dates[0])} – {_day(dates[-1], True)}" if dates else "—"


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_etl_pdf(etl: Dict[str, Any], out_path: Path) -> Path:
    """Build the ETL run report (Part 1)."""
    c = etl.get("counts", {})
    cover = {
        "eyebrow": "ETL run report",
        "title_lines": ["Extract, validate,", "load."],
        "subtitle_lines": [f"NASA FIRMS {etl.get('api_source', '')} · {etl.get('day_range', '—')}-day window",
                           f"Run {etl.get('run_id', '—')}"],
        "metrics": [(_fmt(c.get("raw_rows_extracted")), "extracted"), (_fmt(c.get("valid_records")), "valid"),
                    (_fmt(c.get("inserted_records")), "inserted"), (_fmt(c.get("skipped_existing_records")), "skipped (duplicates)")],
        "details": _cover_details(etl, [("Run started", _datetime(etl.get("started_at")))]),
        "header_right": _datetime(etl.get("started_at")),
    }
    return _build(out_path, "ETL Run Report", cover, _sec_etl(etl, "01") + _sec_limitations("02"))


def build_analysis_pdf(analysis: Dict[str, Any], charts_dir: Optional[Path], out_path: Path,
                       etl: Optional[Dict[str, Any]] = None) -> Path:
    """Build the EDA and hotspot analysis report (Part 2)."""
    ov = analysis.get("eda_results", {}).get("overview", {})
    grid = analysis.get("grid_metadata", {})
    frp = analysis.get("eda_results", {}).get("distributions", {}).get("frp", {})
    cover = {
        "eyebrow": "Exploratory data analysis",
        "title_lines": ["Where the Amazon", "burned."],
        "subtitle_lines": [f"{_window_text(analysis)} · VIIRS NOAA-21 active-fire detections",
                           "Distributions, timing and 0.25° hotspot ranking"],
        "metrics": [(_fmt(ov.get("total_records")), "detections analysed"),
                    (_fmt(grid.get("total_populated_cells")), "grid cells"),
                    (_fmt(grid.get("high_priority_count")), "high-priority cells"),
                    (_fmt(frp.get("outlier_count")) if frp.get("available") else "—", "FRP outliers")],
        "details": _cover_details(etl, [("Generated from", "Supabase table fire_detections"),
                                        ("Analysis run", _datetime(analysis.get("generated_at")))]),
        "header_right": _window_text(analysis),
    }
    charts = Path(charts_dir) if charts_dir else None
    story = (_sec_overview(analysis, "01") + _sec_distributions(analysis, charts, "02") +
             _sec_timing(analysis, charts, "03") + _sec_hotspots(analysis, charts, "04") + _sec_limitations("05"))
    return _build(out_path, "Analysis Report", cover, story)


def build_conservation_pdf(cons: Dict[str, Any], charts_dir: Optional[Path], out_path: Path) -> Path:
    """Build the GBIF biodiversity comparison report (Part 3)."""
    s = cons.get("summary_metrics", {})
    meta = cons.get("metadata", {})
    cover = {
        "eyebrow": "Biodiversity comparison",
        "title_lines": ["Fire meets", "wildlife."],
        "subtitle_lines": ["GBIF animal occurrences in Medium and High fire-priority cells",
                           f"Run {meta.get('run_id', '—')}"],
        "metrics": [(_fmt(s.get("priority_cells_considered")), "cells queried"),
                    (_fmt(s.get("gbif_occurrence_records_received")), "GBIF records"),
                    (_fmt(s.get("unique_animal_species_found")), "unique species"),
                    (_fmt(s.get("species_with_verified_iucn_status")), "IUCN verified")],
        "details": [("Generated", _datetime(meta.get("generated_at"))),
                    ("Database project", meta.get("database_project") or meta.get("firebase_project_id") or "—"),
                    ("Privacy", "aggregated to 0.25° cells, no point coordinates")],
        "header_right": _datetime(meta.get("generated_at")),
    }
    charts = Path(charts_dir) if charts_dir else None
    return _build(out_path, "Biodiversity Report", cover,
                  _sec_biodiversity(cons, charts, "01") + _sec_limitations("02"))


def build_project_pdf(etl: Optional[Dict[str, Any]], analysis: Dict[str, Any], analysis_charts: Optional[Path],
                      cons: Optional[Dict[str, Any]], cons_charts: Optional[Path], out_path: Path,
                      cons_stale: bool = False) -> Path:
    """Build the complete project report: problem, method, all six EDA goals and limitations."""
    ov = analysis.get("eda_results", {}).get("overview", {})
    grid = analysis.get("grid_metadata", {})
    charts = Path(analysis_charts) if analysis_charts else None
    cover = {
        "eyebrow": "Project report · Fire data ETL and EDA for the Amazon",
        "title_lines": ["ForestSentinel"],
        "subtitle_lines": ["Satellite fire detections, cleaned, stored and explored",
                           f"{_window_text(analysis)} · NASA FIRMS VIIRS NOAA-21 · GBIF"],
        "metrics": [(_fmt(ov.get("total_records")), "detections analysed"),
                    (_fmt(grid.get("total_populated_cells")), "0.25° grid cells"),
                    (_fmt(grid.get("high_priority_count")), "high-priority cells"),
                    (_fmt((cons or {}).get("summary_metrics", {}).get("unique_animal_species_found")), "animal species (GBIF)")],
        "details": _cover_details(etl, [("Study window", _window_text(analysis))]),
        "header_right": _window_text(analysis),
    }

    story: List[Flowable] = _section("00", "About this project")
    story += [Paragraph("Problem", S_H2), Paragraph(
        "Satellite fire data arrives as thousands of raw points, which makes it hard to see where fire activity "
        "concentrates. ForestSentinel cleans these detections, stores them properly and explores them to find "
        "patterns and hotspots. It is an analysis of past detections, not a fire prediction model.", S_BODY)]
    story += [Paragraph("Dataset", S_H2), Paragraph(
        "NASA FIRMS active-fire data from the VIIRS instrument on NOAA-21, requested through the FIRMS Area API for "
        "the Amazon study area over the last five days. It is real, regularly updated data with the columns needed "
        "for EDA: location, date, time, Fire Radiative Power, brightness and confidence. GBIF animal occurrence "
        "records are added for the highest-priority fire areas.", S_BODY)]
    story += [Paragraph("Pipeline", S_H2), _table(["Step", "What it does"], [
        ["Extract", "requests calls the FIRMS API; the raw response is archived as CSV."],
        ["Transform", "pandas standardises columns, parses UTC timestamps and drops exact duplicates."],
        ["Validate", "Pydantic v2 checks every record; failures are stored separately in rejected_records."],
        ["Load", "Supabase, keyed by a deterministic SHA-256 hash so reruns never duplicate data."],
        ["Explore", "EDA, 0.25° grid scoring, Matplotlib/Seaborn charts, a Folium map and GBIF comparison."],
    ], [28 * mm, CONTENT_W - 28 * mm]), Spacer(1, 5 * mm)]

    goals = [
        ("1", "Data quality check (extracted, cleaned, rejected, loaded counts)", "Section 01 · ETL record flow"),
        ("2", "Distributions of FRP, brightness and confidence, with outliers", "Section 03 · IQR outliers, box plots"),
        ("3", "Detections per day and per hour, day vs night", "Section 04 · daily, hourly, day/night"),
        ("4", "0.25° grid cells ranked High, Medium or Low", "Section 05 · priority score"),
        ("5", "Charts with Matplotlib/Seaborn and an interactive Folium map", "Figures throughout · map in dashboard"),
        ("6", "Compare fire areas with GBIF animal data at grid level",
         "Section 06" + (" · refresh pending" if cons_stale else "") if cons else "Run Part 3 to add"),
    ]
    done = colors.HexColor("#16a34a").hexval().replace("0x", "#")
    story += [Paragraph("EDA goals covered", S_H2), _table(["#", "Goal from the proposal", "Status", "Where"], [
        [g, goal, Paragraph(f"<font color='{done}'>●</font> Done" if (g != "6" or cons) else "Pending", S_CELL), where]
        for g, goal, where in goals], [8 * mm, 88 * mm, 22 * mm, CONTENT_W - 118 * mm])]

    if etl:
        story += _sec_etl(etl, "01")
    story += _sec_overview(analysis, "02") + _sec_distributions(analysis, charts, "03") + \
        _sec_timing(analysis, charts, "04") + _sec_hotspots(analysis, charts, "05")
    if cons:
        story += _sec_biodiversity(cons, Path(cons_charts) if cons_charts else None, "06", stale=cons_stale)
    story += _sec_limitations("07")
    return _build(out_path, "Project Report", cover, story)


def load_json(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Read a JSON report, or None if it is missing or unreadable."""
    import json
    if not path or not Path(path).exists():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Could not read report %s: %s", path, exc)
        return None


def latest_etl_report(reports_dir: Path) -> Optional[Dict[str, Any]]:
    """The newest ETL JSON report in ``reports_dir`` (timestamped names sort chronologically)."""
    matches = sorted(Path(reports_dir).glob("etl_report_*.json"))
    return load_json(matches[-1]) if matches else None


def try_build(builder: Any, *args: Any, **kwargs: Any) -> Optional[Path]:
    """Run a builder without letting a PDF failure break the pipeline that called it."""
    try:
        return builder(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive; PDF is a by-product
        logger.warning("PDF report could not be generated: %s", exc)
        return None
