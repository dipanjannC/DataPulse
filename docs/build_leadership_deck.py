"""DataPulse leadership deck — visual-first edition.

Design rules enforced throughout:
  · one idea per slide, carried by a diagram
  · text is labels, never paragraphs (hard cap ~14 words per element)
  · white canvas, Accenture purple accent, two support hues
      purple = the graph plans   ·   blue = the database executes
  · every coordinate derives from one grid, so nothing needs hand-nudging
"""
from __future__ import annotations

import math

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

OUT = r"c:\Data_pulse_kg\DataPulse_Leadership_Deck.pptx"

# ── palette ─────────────────────────────────────────────────────────────────
BG        = RGBColor(0xFF, 0xFF, 0xFF)
PAPER     = RGBColor(0xFA, 0xFA, 0xFC)
SURFACE   = RGBColor(0xF6, 0xF6, 0xF9)
SURFACE2  = RGBColor(0xEF, 0xEF, 0xF4)
BORDER    = RGBColor(0xE1, 0xE1, 0xE9)
BORDER_HI = RGBColor(0xC6, 0xC6, 0xD2)
ACCENT    = RGBColor(0xA1, 0x00, 0xFF)
ACCENT_TX = RGBColor(0x6D, 0x00, 0xB3)
ACCENT_DK = RGBColor(0x4A, 0x00, 0x7A)
KG        = RGBColor(0x6D, 0x00, 0xB3)
SQL       = RGBColor(0x0A, 0x6B, 0xAF)
TEXT      = RGBColor(0x11, 0x11, 0x19)
DIM       = RGBColor(0x45, 0x45, 0x4F)
MUTED     = RGBColor(0x78, 0x78, 0x8A)
TEAL      = RGBColor(0x0B, 0x7C, 0x63)
WARN      = RGBColor(0xA6, 0x5E, 0x0A)
ERR       = RGBColor(0xBE, 0x2F, 0x2A)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)

# purple tints for funnels / heat ramps (light → deep)
T1 = RGBColor(0xEE, 0xDD, 0xFB)
T2 = RGBColor(0xD5, 0xB0, 0xF6)
T3 = RGBColor(0xB0, 0x6E, 0xEC)
T4 = RGBColor(0x8A, 0x28, 0xDE)

SANS  = "Segoe UI"
LIGHT = "Segoe UI Light"
MONO  = "Consolas"

SW, SH = 13.333, 7.5
M      = 0.60
CW     = SW - 2 * M
CXC    = M + CW / 2          # horizontal centre of the content column
FOOT_Y = 6.99

prs = Presentation()
prs.slide_width  = Inches(SW)
prs.slide_height = Inches(SH)
BLANK = prs.slide_layouts[6]
_n = [0]


# ── primitives ──────────────────────────────────────────────────────────────

def _style(shape, fill=None, line=None, lw=1.0):
    shape.shadow.inherit = False
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(lw)
    if shape.has_text_frame:
        shape.text_frame.word_wrap = True
    return shape


def new_slide(fill=BG):
    s = prs.slides.add_slide(BLANK)
    _style(s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(SW), Inches(SH)),
           fill=fill, line=None)
    return s


def rect(s, x, y, w, h, fill=SURFACE, line=BORDER, lw=1.0, shape=MSO_SHAPE.RECTANGLE,
         rot=None):
    sh = _style(s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h)),
                fill, line, lw)
    if rot is not None:
        sh.rotation = rot
    return sh


def grad(s, x, y, w, h, c1, c2, angle=0.0, shape=MSO_SHAPE.RECTANGLE):
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.shadow.inherit = False
    sh.line.fill.background()
    try:
        f = sh.fill
        f.gradient()
        f.gradient_stops[0].color.rgb = c1
        f.gradient_stops[0].position = 0.0
        f.gradient_stops[1].color.rgb = c2
        f.gradient_stops[1].position = 1.0
        f.gradient_angle = angle
    except Exception:                     # any renderer quirk → flat brand fill
        sh.fill.solid()
        sh.fill.fore_color.rgb = c1
    if sh.has_text_frame:
        sh.text_frame.word_wrap = True
    return sh


def tracking(run, pts):
    run.font._rPr.set("spc", str(int(pts * 100)))


def text(s, x, y, w, h, spans, size=10.5, color=DIM, bold=False, font=SANS,
         align=PP_ALIGN.LEFT, ls=1.24, anchor=MSO_ANCHOR.TOP, spc=0.0):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    paras = [spans] if isinstance(spans, str) else spans
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = ls
        runs = [(para, {})] if isinstance(para, str) else para
        runs = [(r, {}) if isinstance(r, str) else r for r in runs]
        for txt, ov in runs:
            r = p.add_run()
            r.text = txt
            f = r.font
            f.name = ov.get("font", font)
            f.size = Pt(ov.get("size", size))
            f.bold = ov.get("bold", bold)
            f.color.rgb = ov.get("color", color)
            t = ov.get("spc", spc)
            if t:
                tracking(r, t)
    return tb


def ctext(s, x, y, w, h, spans, **kw):
    kw.setdefault("align", PP_ALIGN.CENTER)
    return text(s, x, y, w, h, spans, **kw)


def label_in(s, shape_x, shape_y, shape_w, shape_h, spans, size=10.5, color=TEXT,
            bold=True, font=SANS, ls=1.10):
    """Centre a label inside a drawn shape's bounds (own textbox = full control)."""
    return text(s, shape_x, shape_y, shape_w, shape_h, spans, size=size, color=color,
                bold=bold, font=font, align=PP_ALIGN.CENTER, ls=ls,
                anchor=MSO_ANCHOR.MIDDLE)


def eyebrow(s, x, y, label, color=ACCENT_TX, w=None, size=8.5):
    text(s, x, y, w or 7.0, 0.20, label.upper(), size=size, color=color, bold=True, spc=1.3)


def header(s, kicker, title):
    """Compact header — one kicker, one title, one rule. No paragraph subtitle."""
    rect(s, M, 0.44, 0.055, 0.30, fill=ACCENT, line=None)
    eyebrow(s, M + 0.17, 0.47, kicker)
    text(s, M, 0.70, CW, 0.46, title, size=25, color=TEXT, bold=True, ls=1.0)
    rect(s, M, 1.34, CW, 0.014, fill=ACCENT, line=None)
    return 1.34


def footer(s, label="DataPulse  ·  Knowledge-Graph Grounded Text-to-SQL"):
    _n[0] += 1
    text(s, M, FOOT_Y, 8.0, 0.20, label, size=8, color=MUTED, spc=0.4)
    text(s, SW - M - 2.0, FOOT_Y, 2.0, 0.20, f"{_n[0]:02d}", size=8, color=ACCENT_TX,
         align=PP_ALIGN.RIGHT, bold=True)


def cols(n, gap=0.24, x0=M, total=CW):
    w = (total - gap * (n - 1)) / n
    return [(x0 + i * (w + gap), w) for i in range(n)]


def arrow(s, x, y, w, h, shape=MSO_SHAPE.RIGHT_ARROW, color=BORDER_HI, rot=None):
    return rect(s, x, y, w, h, fill=color, line=None, shape=shape, rot=rot)


def line(s, x1, y1, x2, y2, color=BORDER_HI, w=1.25, dash=False):
    ln = s.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    ln.line.color.rgb = color
    ln.line.width = Pt(w)
    if dash:
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        ln.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    return ln


def node(s, x, y, w, h, title, sub=None, color=KG, fill=WHITE, tsize=10.6,
         shape=MSO_SHAPE.ROUNDED_RECTANGLE, mono=False):
    """A graph node: outlined chip with a bold label and optional caption."""
    rect(s, x, y, w, h, fill=fill, line=color, lw=1.5, shape=shape)
    if sub:
        text(s, x, y + h / 2 - 0.30, w, 0.24, title, size=tsize, color=color, bold=True,
             font=MONO if mono else SANS, align=PP_ALIGN.CENTER, ls=1.0)
        text(s, x, y + h / 2 + 0.00, w, 0.20, sub, size=7.8, color=MUTED,
             align=PP_ALIGN.CENTER, ls=1.0)
    else:
        label_in(s, x, y, w, h, title, size=tsize, color=color,
                 font=MONO if mono else SANS)
    return (x + w / 2, y + h / 2)


def hero(s, x, y, w, value, label, color=ACCENT_TX, vsize=54, lsize=9):
    ctext(s, x, y, w, 0.80, value, size=vsize, color=color, bold=True, font=LIGHT, ls=0.98)
    ctext(s, x, y + 0.86, w, 0.24, label.upper(), size=lsize, color=MUTED, bold=True, spc=1.2, ls=1.0)


def tile(s, x, y, w, h, value, label, color=ACCENT_TX, vsize=20):
    rect(s, x, y, w, h, fill=SURFACE, line=BORDER)
    rect(s, x, y, w, 0.05, fill=color, line=None)
    ctext(s, x, y + h * 0.26, w, 0.34, value, size=vsize, color=TEXT, bold=True, ls=1.0)
    ctext(s, x, y + h * 0.66, w, 0.22, label.upper(), size=7.8, color=color, bold=True,
          spc=0.9, ls=1.0)


def divider(s_kicker, s_title, s_sub, num):
    """Full-bleed purple section break — gives the deck rhythm."""
    s = new_slide()
    grad(s, 0, 0, SW, SH, ACCENT_DK, ACCENT, angle=315.0)
    ctext(s, 0, 0, SW, 0.0, "")
    text(s, M + 0.10, 2.62, 3.0, 1.40, num, size=110, color=RGBColor(0xC9, 0x8A, 0xF5),
         bold=True, font=LIGHT, ls=0.9)
    rect(s, M + 2.30, 2.86, 0.02, 1.10, fill=RGBColor(0xC9, 0x8A, 0xF5), line=None)
    eyebrow(s, M + 2.66, 2.92, s_kicker, color=RGBColor(0xE4, 0xC6, 0xFC), w=7.0)
    text(s, M + 2.66, 3.20, 9.2, 0.60, s_title, size=34, color=WHITE, bold=True, ls=1.0)
    text(s, M + 2.66, 3.92, 8.6, 0.30, s_sub, size=13, color=RGBColor(0xDD, 0xBC, 0xF8), ls=1.0)
    _n[0] += 1
    return s


# ═══════════════════════════════════════════════════════════════════════════
# 01 — Title
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide(PAPER)
grad(s, 0, 0, SW, 0.16, ACCENT_DK, ACCENT, angle=0.0)

# living graph motif, right side
NODES = [(9.55, 1.62, .20), (11.25, 1.28, .13), (12.35, 2.05, .11), (10.40, 2.60, .16),
         (11.95, 3.10, .13), (9.30, 3.35, .12), (10.85, 4.02, .19), (12.45, 4.35, .11),
         (9.95, 4.85, .12), (11.55, 5.15, .14)]
EDGES = [(0, 1), (0, 3), (1, 2), (2, 4), (3, 4), (3, 5), (4, 6), (5, 6), (6, 7), (6, 8),
         (6, 9), (7, 9), (8, 9)]
for a, b in EDGES:
    x1, y1, r1 = NODES[a]
    x2, y2, r2 = NODES[b]
    line(s, x1 + r1 / 2, y1 + r1 / 2, x2 + r2 / 2, y2 + r2 / 2,
         color=RGBColor(0xE0, 0xC8, 0xF6), w=1.1)
for i, (nx, ny, r_) in enumerate(NODES):
    c = ACCENT if r_ >= 0.16 else RGBColor(0xC1, 0x7C, 0xF0)
    rect(s, nx, ny, r_, r_, fill=c, line=None, shape=MSO_SHAPE.OVAL)

rect(s, M, 1.70, 0.055, 0.34, fill=ACCENT, line=None)
eyebrow(s, M + 0.17, 1.74, "Enterprise Data Intelligence  ·  Technical Briefing", w=8.0)

text(s, M, 2.28, 8.6, 0.90, [[("Data", {"font": LIGHT, "color": TEXT}),
                              ("Pulse", {"bold": True, "color": ACCENT_TX})]],
     size=62, ls=0.95)
text(s, M, 3.34, 8.4, 0.44, "Ask your data. In plain English.",
     size=25, color=TEXT, bold=True, ls=1.0)
rect(s, M, 4.00, 3.6, 0.014, fill=ACCENT, line=None)
text(s, M, 4.26, 7.9, 0.72,
     [[("The graph plans the query.", {"color": ACCENT_TX, "bold": True})],
      [("The database answers it.", {"color": DIM})]], size=17, ls=1.34)

for i, (x, w) in enumerate(cols(4, gap=0.20, total=8.0)):
    v, l = [("5", "domains"), ("50", "tables"), ("23,293", "rows"), ("441", "graph nodes")][i]
    tile(s, x, 5.62, w, 0.90, v, l, vsize=18)

text(s, M, 6.86, 9.0, 0.24, "Neo4j   ·   LLaMA-3.3-70B on Groq   ·   FastAPI   ·   SQLite",
     size=9.5, color=MUTED, spc=0.5)
_n[0] += 1

# ═══════════════════════════════════════════════════════════════════════════
# 02 — The promise, in one line
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
rect(s, 0, 0, SW, 0.16, fill=ACCENT, line=None)
text(s, M, 1.62, 12.0, 2.30,
     [[("A business question in,", {"color": TEXT})],
      [("verified SQL out —", {"color": TEXT})],
      [("and the reasoning shown.", {"color": ACCENT_TX, "bold": True})]],
     size=46, ls=1.20, font=LIGHT)
rect(s, M, 4.34, 5.0, 0.014, fill=ACCENT, line=None)

flow = [("Question", "plain English", MUTED),
        ("Knowledge graph", "finds the schema", KG),
        ("Agent", "writes the SQL", ACCENT_TX),
        ("Database", "returns the rows", SQL),
        ("Answer", "with its evidence", TEAL)]
fy, fh = 4.70, 0.92
CH_W = (CW - 4 * 0.10) / 5
for i, (t, sub, c) in enumerate(flow):
    x = M + i * (CH_W + 0.10)
    rect(s, x, fy, CH_W, fh, fill=SURFACE if i else SURFACE2, line=BORDER,
         shape=MSO_SHAPE.CHEVRON)
    ctext(s, x + 0.16, fy + 0.24, CH_W - 0.32, 0.24, t, size=12, color=c, bold=True, ls=1.0)
    ctext(s, x + 0.16, fy + 0.52, CH_W - 0.32, 0.20, sub, size=8.6, color=MUTED, ls=1.0)
ctext(s, M, fy + fh + 0.34, CW, 0.24,
      "No SQL. No ticket. No waiting for someone who knows the schema.",
      size=12, color=DIM, ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 03 — DIVIDER: the problem
# ═══════════════════════════════════════════════════════════════════════════
divider("Section one", "The Problem", "Everyone has the data. Almost nobody can reach it.", "01")

# ═══════════════════════════════════════════════════════════════════════════
# 04 — The wall  (diagram)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "The Problem", "A question, and the wall between it and the answer")

# question side
node(s, M, 3.15, 2.35, 1.00, "The question", "one plain sentence", color=MUTED, tsize=12)
arrow(s, M + 2.50, 3.55, 0.55, 0.20, color=BORDER_HI)

# the wall
WX, WW = 4.10, 4.60
grad(s, WX, 2.10, WW, 3.10, RGBColor(0xF3, 0xE6, 0xFC), RGBColor(0xE0, 0xC4, 0xF8), angle=90.0)
rect(s, WX, 2.10, WW, 0.05, fill=ERR, line=None)
ctext(s, WX, 2.32, WW, 0.24, "THE TRANSLATION LAYER", size=9, color=ERR, bold=True, spc=1.2, ls=1.0)
walls = [("50", "tables to choose from"), ("373", "columns to disambiguate"),
         ("40", "join keys, none in the DDL"), ("1", "definition of “revenue”, contested")]
for i, (v, l) in enumerate(walls):
    ry = 2.68 + i * 0.60
    rect(s, WX + 0.26, ry, WW - 0.52, 0.50, fill=WHITE, line=BORDER)
    text(s, WX + 0.44, ry + 0.11, 0.86, 0.28, v, size=15, color=ACCENT_TX, bold=True, ls=1.0)
    text(s, WX + 1.42, ry + 0.15, WW - 1.90, 0.24, l, size=9.6, color=DIM, ls=1.0)

# bounce-off arrow
arrow(s, WX + WW + 0.16, 3.55, 0.55, 0.20, color=RGBColor(0xE8, 0xC9, 0xC8))
node(s, WX + WW + 0.90, 3.15, 2.35, 1.00, "The answer", "days later, if at all",
     color=BORDER_HI, tsize=12)

# the human bottleneck, underneath
by = 5.52
rect(s, M, by, CW, 0.86, fill=SURFACE2, line=ACCENT, lw=1.4)
rect(s, M, by, 0.055, 0.86, fill=ACCENT, line=None)
text(s, M + 0.32, by + 0.16, CW - 0.72, 0.30,
     [[("The wall is not technical. ", {"color": ACCENT_TX, "bold": True, "size": 13}),
       ("It is a person — the analyst who holds all four of those facts in their head.",
        {"color": TEXT, "size": 13})]], ls=1.0)
text(s, M + 0.32, by + 0.50, CW - 0.72, 0.24,
     "That person is the bottleneck, and there are never enough of them.",
     size=10.4, color=MUTED, ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 05 — Days vs seconds  (hero contrast)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "The Cost", "The same question, two worlds")

for i, (side, tone, when, num, unit, cap, rows) in enumerate([
    ("left", ERR, "TODAY", "4", "days", "question → ticket → queue → analyst → spreadsheet",
     ["Filed, queued, seventh in line", "An analyst reverse-engineers the joins",
      "A number arrives, with a caveat", "The decision has already been made"]),
    ("right", TEAL, "WITH DATAPULSE", "8", "seconds", "question → graph → agent → answer",
     ["Asked in the browser, in plain English", "The graph returns the exact join keys",
      "The agent writes and runs the SQL", "The answer arrives with its evidence"]),
]):
    x, w = cols(2, gap=0.50)[i]
    rect(s, x, 1.62, w, 4.72, fill=SURFACE if i == 0 else PAPER, line=BORDER)
    rect(s, x, 1.62, w, 0.05, fill=tone, line=None)
    ctext(s, x, 1.86, w, 0.24, when, size=9, color=tone, bold=True, spc=1.3, ls=1.0)
    ctext(s, x, 2.24, w, 1.10,
          [[(num, {"size": 82, "color": tone, "bold": True, "font": LIGHT}),
            ("  " + unit, {"size": 22, "color": MUTED, "font": LIGHT})]], ls=0.95)
    ctext(s, x + 0.30, 3.48, w - 0.60, 0.24, cap, size=9.4, color=MUTED, ls=1.0)
    rect(s, x + 0.60, 3.86, w - 1.20, 0.006, fill=BORDER, line=None)
    for j, r in enumerate(rows):
        ry = 4.04 + j * 0.50
        rect(s, x + 0.42, ry + 0.055, 0.16, 0.16, fill=tone, line=None, shape=MSO_SHAPE.OVAL)
        text(s, x + 0.74, ry, w - 1.16, 0.30, r, size=10, color=DIM, ls=1.14)

# the multiplier
ctext(s, M, 6.50, CW, 0.28,
      [[("Roughly ", {"color": DIM, "size": 12}),
        ("43,000× faster", {"color": ACCENT_TX, "bold": True, "size": 13.5}),
        (" — and the analyst is freed for work only they can do.", {"color": DIM, "size": 12})]],
      ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 06 — Four silent failures  (icon tiles, minimal words)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Why LLMs Alone Fail", "Four ways confident SQL goes quietly wrong")

fails = [("01", "Too much schema", "373 columns in the prompt.\nAttention spreads thin.",
          "picks a plausible wrong column"),
         ("02", "Invented joins", "Foreign keys are not in\nthe DDL the model sees.",
          "guesses the key, skews the count"),
         ("03", "Contested words", "“Revenue” matches two\nnumeric columns.",
          "3.8× apart — both look right"),
         ("04", "No evidence", "One opaque generation.\nNothing to inspect.",
          "confident, and unauditable")]
for i, (n, t, b, tag) in enumerate(fails):
    x, w = cols(4)[i]
    rect(s, x, 1.62, w, 3.46, fill=SURFACE, line=BORDER)
    rect(s, x, 1.62, w, 0.05, fill=ERR, line=None)
    # big ghost numeral
    text(s, x + 0.24, 1.82, 1.40, 0.90, n, size=44, color=RGBColor(0xEC, 0xD9, 0xD8),
         bold=True, font=LIGHT, ls=0.95)
    text(s, x + 0.26, 2.86, w - 0.52, 0.32, t, size=14, color=TEXT, bold=True, ls=1.04)
    text(s, x + 0.26, 3.34, w - 0.52, 0.70, b, size=10.4, color=DIM, ls=1.30)
    rect(s, x + 0.26, 4.34, w - 0.52, 0.006, fill=BORDER, line=None)
    text(s, x + 0.26, 4.50, w - 0.52, 0.44, tag, size=9.4, color=ERR, bold=True, ls=1.16)

yb = 5.34
rect(s, M, yb, CW, 1.02, fill=SURFACE2, line=ACCENT, lw=1.4)
rect(s, M, yb, 0.055, 1.02, fill=ACCENT, line=None)
text(s, M + 0.32, yb + 0.20, CW - 0.72, 0.30,
     "All four are one failure: the model is asked to plan a query with no map of the schema.",
     size=14.5, color=TEXT, bold=True, ls=1.0)
text(s, M + 0.32, yb + 0.60, CW - 0.72, 0.26,
     "The fix is not a bigger model. It is giving the model the structure as fact.",
     size=11.4, color=ACCENT_TX, ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 07 — The revenue trap  (two-path diagram, almost no prose)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Failure 03, In Detail", "One question. Two columns. A 3.8× gap.")

node(s, M, 3.28, 2.90, 0.86, "“total revenue?”", color=TEXT, tsize=13)
line(s, M + 2.90, 3.71, 4.20, 2.62, color=BORDER_HI)
line(s, M + 2.90, 3.71, 4.20, 4.82, color=BORDER_HI)

paths = [(2.28, "invoices.amount", "$2,030,281.53", "WRONG", ERR,
          "invoiced to date — a different question"),
         (4.48, "order_items.line_total", "$7,782,964.89", "CORRECT", TEAL,
          "the canonical revenue measure")]
for (py, col, val, verdict, tone, note) in paths:
    rect(s, 4.20, py, 6.05, 0.86, fill=WHITE, line=tone, lw=1.6)
    rect(s, 4.20, py, 0.05, 0.86, fill=tone, line=None)
    text(s, 4.44, py + 0.14, 3.10, 0.24, col, size=11.2, color=TEXT, bold=True, font=MONO, ls=1.0)
    text(s, 4.44, py + 0.44, 3.10, 0.22, note, size=8.8, color=MUTED, ls=1.0)
    text(s, 7.66, py + 0.24, 1.66, 0.34, val, size=15, color=tone, bold=True, ls=1.0)
    rect(s, 10.45, py + 0.26, 1.30, 0.34, fill=tone, line=None)
    label_in(s, 10.45, py + 0.26, 1.30, 0.34, verdict, size=8.6, color=WHITE)

# the resolver
ry = 5.62
rect(s, M, ry, CW, 0.94, fill=SURFACE2, line=ACCENT, lw=1.4)
rect(s, M, ry, 0.055, 0.94, fill=ACCENT, line=None)
text(s, M + 0.32, ry + 0.14, 5.20, 0.26, "HOW THE GRAPH SETTLES IT", size=8.8,
     color=ACCENT_TX, bold=True, spc=1.2, ls=1.0)
text(s, M + 0.32, ry + 0.44, 5.30, 0.30,
     "13 canonical metrics, stored as nodes.", size=12, color=TEXT, bold=True, ls=1.0)
rect(s, M + 6.00, ry + 0.22, 5.85, 0.50, fill=WHITE, line=BORDER)
text(s, M + 6.20, ry + 0.36, 5.50, 0.24, "total revenue  =  SUM(order_items.line_total)",
     size=10.4, color=SQL, bold=True, font=MONO, ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 08 — DIVIDER: the design
# ═══════════════════════════════════════════════════════════════════════════
divider("Section two", "The Design", "Separate the plan from the data. Everything follows.", "02")

# ═══════════════════════════════════════════════════════════════════════════
# 09 — The big idea  (split brain)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "The Core Idea", "Two stores. Two jobs. Never confused.")

for i, (t, verb, sub, rows, c) in enumerate([
    ("Neo4j", "PLANS", "the knowledge graph",
     [("441", "nodes of schema metadata"), ("40", "join edges with exact keys"),
      ("3", "vector indexes, 384-d"), ("0", "rows of business data")], KG),
    ("SQLite", "EXECUTES", "the execution store",
     [("23,293", "rows of business data"), ("50", "tables, opened read-only"),
      ("5 s", "statement timeout"), ("0", "writes ever permitted")], SQL),
]):
    x, w = cols(2, gap=0.70)[i]
    rect(s, x, 1.62, w, 4.10, fill=SURFACE, line=c, lw=1.6)
    rect(s, x, 1.62, w, 0.06, fill=c, line=None)
    ctext(s, x, 1.90, w, 0.44, t, size=27, color=c, bold=True, font=LIGHT, ls=1.0)
    ctext(s, x, 2.40, w, 0.24, sub, size=9.4, color=MUTED, ls=1.0)
    rect(s, x + w / 2 - 0.90, 2.78, 1.80, 0.40, fill=c, line=None)
    label_in(s, x + w / 2 - 0.90, 2.78, 1.80, 0.40, verb, size=11.4, color=WHITE)
    for j, (v, l) in enumerate(rows):
        ry2 = 3.42 + j * 0.54
        rect(s, x + 0.34, ry2, w - 0.68, 0.006, fill=BORDER, line=None)
        text(s, x + 0.34, ry2 + 0.12, 1.34, 0.28, v, size=14, color=TEXT, bold=True, ls=1.0)
        text(s, x + 1.80, ry2 + 0.17, w - 2.16, 0.24, l, size=9.8, color=DIM, ls=1.0)

# the seam
cxm = M + cols(2, gap=0.70)[0][1] + 0.35
line(s, cxm, 1.90, cxm, 5.44, color=BORDER_HI)
rect(s, cxm - 0.42, 3.44, 0.84, 0.46, fill=WHITE, line=BORDER_HI)
label_in(s, cxm - 0.42, 3.44, 0.84, 0.46, "vs", size=10, color=MUTED)

ctext(s, M, 5.96, CW, 0.30,
      [[("Row values live only in SQLite. ", {"color": DIM, "size": 12.5}),
        ("So regenerating the data never rebuilds the graph.",
         {"color": ACCENT_TX, "bold": True, "size": 12.5})]], ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 10 — Knowledge graph anatomy  (real node-link diagram)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Inside The Graph", "What the schema looks like as a graph")

# ── left: the drawn graph ──
GX = M
d_c = node(s, GX, 3.22, 1.34, 0.54, ":Domain", "Sales", color=ACCENT, tsize=9.6, mono=True)

TBX, TBW, TBH = 2.44, 1.86, 0.52
tbl = [("customers", 2.06), ("orders", 3.23), ("order_items", 4.40)]
tcent = []
for name, ty in tbl:
    tcent.append(node(s, TBX, ty, TBW, TBH, name, color=KG, tsize=10, mono=True))
    line(s, GX + 1.34, 3.49, TBX, ty + TBH / 2, color=RGBColor(0xC4, 0x9B, 0xEC))

# :REFERENCES edges (child → parent) with the join keys
for (frm, to, key) in [(1, 0, "customer_id"), (2, 1, "order_id")]:
    xa = TBX + TBW / 2
    line(s, xa, tbl[frm][1], xa, tbl[to][1] + TBH, color=ACCENT, w=1.75)
    arrow(s, xa - 0.075, tbl[to][1] + TBH + 0.02, 0.15, 0.14, MSO_SHAPE.UP_ARROW, ACCENT)
    text(s, xa + 0.18, tbl[to][1] + TBH + 0.14, 1.60, 0.20, key, size=8, color=ACCENT_TX,
         bold=True, font=MONO, ls=1.0)

# :HAS_COLUMN fan-out from orders
CBX, CBW, CBH = 4.86, 1.66, 0.34
for i, cn in enumerate(["order_id", "customer_id", "order_date"]):
    cy2 = 2.86 + i * 0.44
    rect(s, CBX, cy2, CBW, CBH, fill=SURFACE, line=BORDER)
    label_in(s, CBX, cy2, CBW, CBH, cn, size=8.4, color=DIM, font=MONO)
    line(s, TBX + TBW, tbl[1][1] + TBH / 2, CBX, cy2 + CBH / 2, color=BORDER_HI, w=1.0)
text(s, CBX, 4.24, CBW, 0.20, "+ 370 more", size=8, color=MUTED, align=PP_ALIGN.CENTER, ls=1.0)

# :Metric node
node(s, GX, 5.06, 1.34, 0.54, ":Metric", "revenue", color=TEAL, tsize=9.6, mono=True)
line(s, GX + 1.34, 5.33, TBX, tbl[2][1] + TBH / 2, color=RGBColor(0xB8, 0xDE, 0xD4), w=1.5)

# legend
LGY = 5.94
rect(s, GX, LGY, 6.62, 0.62, fill=SURFACE, line=BORDER)
leg = [(":HAS_TABLE", RGBColor(0xC4, 0x9B, 0xEC)), (":HAS_COLUMN", BORDER_HI),
       (":REFERENCES", ACCENT), (":OWNS_METRIC", RGBColor(0xB8, 0xDE, 0xD4))]
for i, (nm, c) in enumerate(leg):
    lx = GX + 0.22 + i * 1.62
    rect(s, lx, LGY + 0.29, 0.30, 0.045, fill=c, line=None)
    text(s, lx + 0.40, LGY + 0.21, 1.20, 0.20, nm, size=7.8, color=DIM, font=MONO, ls=1.0)

# ── right: the counts + the payoff ──
RX = 7.42
RW = SW - M - RX
for i, (x, w) in enumerate(cols(2, gap=0.20, x0=RX, total=RW)):
    for j in range(2):
        v, l, c = [[("5", "Domain nodes", KG), ("50", "Table nodes", KG)],
                   [("373", "Column nodes", KG), ("13", "Metric nodes", TEAL)]][j][i]
        tile(s, x, 1.62 + j * 1.02, w, 0.92, v, l, color=c, vsize=19)

rect(s, RX, 3.82, RW, 1.46, fill=SURFACE2, line=ACCENT, lw=1.4)
rect(s, RX, 3.82, 0.055, 1.46, fill=ACCENT, line=None)
text(s, RX + 0.30, 4.02, RW - 0.62, 0.26, "WHY :REFERENCES MATTERS", size=8.8,
     color=ACCENT_TX, bold=True, spc=1.2, ls=1.0)
text(s, RX + 0.30, 4.34, RW - 0.62, 0.80,
     [[("Each edge carries the join columns as properties.", {"color": TEXT, "bold": True, "size": 11.4})],
      [("So “how do these tables join?” stops being a guess and becomes a shortest-path query.",
        {"color": DIM, "size": 10.6})]], ls=1.28)

rect(s, RX, 5.44, RW, 1.12, fill=WHITE, line=BORDER)
text(s, RX + 0.30, 5.62, RW - 0.62, 0.24, "STORED HERE, NEVER GUESSED", size=8.8,
     color=MUTED, bold=True, spc=1.2, ls=1.0)
for i, itm in enumerate(["exact join keys", "canonical metrics", "column aliases"]):
    ix = RX + 0.30 + i * 1.62
    rect(s, ix, 5.98, 0.13, 0.13, fill=ACCENT, line=None, shape=MSO_SHAPE.OVAL)
    text(s, ix + 0.22, 5.92, 1.44, 0.24, itm, size=8.8, color=DIM, ls=1.10)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 11 — Retrieval funnel
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Retrieval", "How 373 columns become the 4 that matter")

bands = [(10.90, "373", "columns across 50 tables", "the whole catalogue", T1, TEXT),
         (8.60, "30", "candidate columns", "vector search + domain boost", T2, TEXT),
         (6.40, "8", "seed tables", "ranked by similarity", T3, WHITE),
         (4.60, "4", "tables · 3 joins", "after path expansion", T4, WHITE)]
BY, BH, BG_ = 1.62, 0.84, 0.18
for i, (bw, num, what, how, fillc, tc) in enumerate(bands):
    y = BY + i * (BH + BG_)
    x = CXC - bw / 2
    rect(s, x, y, bw, BH, fill=fillc, line=None)
    # the numeral column narrows with the band, so the label always has room
    num_w = min(1.55, bw * 0.28)
    lab_x = x + 0.34 + num_w + 0.14
    lab_w = x + bw - 0.30 - lab_x
    text(s, x + 0.34, y + 0.18, num_w, 0.46, num, size=26, color=tc, bold=True,
         font=LIGHT, ls=1.0)
    text(s, lab_x, y + 0.16, lab_w, 0.26, what, size=12.5, color=tc, bold=True, ls=1.0)
    text(s, lab_x, y + 0.46, lab_w, 0.24, how, size=9.4,
         color=tc if tc == WHITE else MUTED, ls=1.0)
    if i < 3:
        arrow(s, CXC - 0.09, y + BH + 0.005, 0.18, 0.17, MSO_SHAPE.DOWN_ARROW, BORDER_HI)

ey = BY + 3 * (BH + BG_) + BH + 0.24
rect(s, M, ey, CW, 0.86, fill=SURFACE2, line=ACCENT, lw=1.4)
rect(s, M, ey, 0.055, 0.86, fill=ACCENT, line=None)
text(s, M + 0.32, ey + 0.16, CW - 0.72, 0.28,
     "The funnel is flat: 8 seed tables whether the catalogue holds 50 or 5,000.",
     size=13.5, color=TEXT, bold=True, ls=1.0)
text(s, M + 0.32, ey + 0.52, CW - 0.72, 0.24,
     "Scale moves out of the prompt and into an indexed vector search.",
     size=10.6, color=ACCENT_TX, ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 12 — The agent loop  (cycle diagram)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "The Reasoning Loop", "The model investigates before it answers")

CCX, CCY = 4.46, 3.74          # cycle centre
NW, NH = 2.02, 0.62
RV, RH_ = 1.56, 1.30           # vertical / horizontal ring radius (to node edge)
ring = [("Model decides", "which tool to call", CCX - NW / 2, CCY - RV - NH / 2),
        ("Tool runs", "graph or database", CCX + RH_, CCY - NH / 2),
        ("Observation", "appended to context", CCX - NW / 2, CCY + RV - NH / 2),
        ("Context grows", "the plan sharpens", CCX - RH_ - NW, CCY - NH / 2)]
for t, sub, nx, ny in ring:
    node(s, nx, ny, NW, NH, t, sub, color=ACCENT_TX, tsize=11)

# centre hub
rect(s, CCX - 0.62, CCY - 0.42, 1.24, 0.84, fill=ACCENT, line=None, shape=MSO_SHAPE.OVAL)
label_in(s, CCX - 0.62, CCY - 0.30, 1.24, 0.32, "≤ 6", size=15, color=WHITE)
label_in(s, CCX - 0.62, CCY + 0.02, 1.24, 0.26, "STEPS", size=7.6, color=RGBColor(0xE9, 0xD2, 0xFB))

# rotating arrows, centred in the four diagonal gaps between the nodes
AW, AH = 0.62, 0.17
for cx_, cy_, rot in [(CCX + 1.16, CCY - 0.94, 45), (CCX + 1.16, CCY + 0.94, 135),
                      (CCX - 1.16, CCY + 0.94, 225), (CCX - 1.16, CCY - 0.94, 315)]:
    arrow(s, cx_ - AW / 2, cy_ - AH / 2, AW, AH, MSO_SHAPE.RIGHT_ARROW, ACCENT, rot=rot)

# right panel — the three tools + the exit
RX2 = 8.24
RW2 = SW - M - RX2
text(s, RX2, 1.66, RW2, 0.24, "THE THREE TOOLS IT MAY CALL", size=8.8, color=ACCENT_TX,
     bold=True, spc=1.2, ls=1.0)
tls = [("get_schema_context", "→ the graph", "tables · join keys · metrics", KG),
       ("sample_values", "→ the database", "real values for a filter", SQL),
       ("run_sql", "→ the database", "read-only SELECT / WITH", SQL)]
for i, (t, dest, sub, c) in enumerate(tls):
    y = 2.00 + i * 0.94
    rect(s, RX2, y, RW2, 0.84, fill=SURFACE, line=BORDER)
    rect(s, RX2, y, 0.05, 0.84, fill=c, line=None)
    text(s, RX2 + 0.24, y + 0.12, RW2 - 0.48, 0.22, t, size=10.6, color=c, bold=True,
         font=MONO, ls=1.0)
    text(s, RX2 + 0.24, y + 0.37, RW2 - 0.48, 0.20, dest, size=8.4, color=MUTED, bold=True, ls=1.0)
    text(s, RX2 + 0.24, y + 0.58, RW2 - 0.48, 0.20, sub, size=8.8, color=DIM, ls=1.0)

rect(s, RX2, 4.90, RW2, 1.14, fill=SURFACE2, line=TEAL, lw=1.4)
rect(s, RX2, 4.90, 0.055, 1.14, fill=TEAL, line=None)
text(s, RX2 + 0.28, 5.08, RW2 - 0.56, 0.24, "THE EXIT CONDITION", size=8.8, color=TEAL,
     bold=True, spc=1.2, ls=1.0)
text(s, RX2 + 0.28, 5.38, RW2 - 0.56, 0.54,
     "No tool call in the reply → that reply is the answer.", size=11, color=TEXT,
     bold=True, ls=1.20)

ctext(s, M, 6.28, CW, 0.28,
      [[("Every turn is recorded. ", {"color": ACCENT_TX, "bold": True, "size": 12.5}),
        ("The reasoning is a trace you can read — not one opaque generation.",
         {"color": DIM, "size": 12.5})]], ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 13 — Join traversal  (path diagram)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Joins", "A guess becomes a graph traversal")

# top: the two worlds
for i, (t, sub, body, c) in enumerate([
    ("Without a graph", "THE MODEL INFERS", "customer_id looks like it joins. Sometimes it does.", ERR),
    ("With the graph", "THE SYSTEM RESOLVES", "shortestPath returns the real keys. Nothing is invented.", TEAL),
]):
    x, w = cols(2, gap=0.36)[i]
    rect(s, x, 1.62, w, 1.20, fill=SURFACE, line=BORDER)
    rect(s, x, 1.62, w, 0.05, fill=c, line=None)
    text(s, x + 0.28, 1.84, w - 0.56, 0.22, sub, size=8.4, color=c, bold=True, spc=1.15, ls=1.0)
    text(s, x + 0.28, 2.10, w - 0.56, 0.28, t, size=14, color=TEXT, bold=True, ls=1.0)
    text(s, x + 0.28, 2.46, w - 0.56, 0.26, body, size=10.2, color=DIM, ls=1.0)

# the traversal itself
TY = 3.14
rect(s, M, TY, CW, 1.86, fill=PAPER, line=BORDER)
text(s, M + 0.32, TY + 0.20, CW - 0.64, 0.24,
     "“REVENUE BY CUSTOMER SEGMENT”  ·  TWO SEEDS, THREE HOPS APART", size=8.8,
     color=ACCENT_TX, bold=True, spc=1.15, ls=1.0)

HW, HH = 2.10, 0.68
GAPW = (CW - 0.68 - 3 * HW) / 2
hx = M + 0.34
hop_y = TY + 0.68
for i, h in enumerate(["customers", "orders", "order_items"]):
    seed = i in (0, 2)
    node(s, hx, hop_y, HW, HH, h, color=SQL if seed else MUTED, tsize=10.6, mono=True,
         fill=WHITE if seed else SURFACE)
    if seed:
        rect(s, hx + HW / 2 - 0.36, hop_y + HH + 0.10, 0.72, 0.22, fill=SQL, line=None)
        label_in(s, hx + HW / 2 - 0.36, hop_y + HH + 0.10, 0.72, 0.22, "SEED",
                 size=7, color=WHITE)
    hx += HW
    if i < 2:
        arrow(s, hx + GAPW / 2 - 0.14, hop_y + HH / 2 - 0.075, 0.28, 0.15, color=ACCENT)
        key = ["orders.customer_id = customers.customer_id",
               "order_items.order_id = orders.order_id"][i]
        ctext(s, hx + 0.06, hop_y - 0.30, GAPW - 0.12, 0.22, key, size=8.2, color=MUTED,
              font=MONO, ls=1.0)
        hx += GAPW
text(s, M + 0.34, TY + 1.54, CW - 0.68, 0.22,
     "The two join conditions reach the prompt as fact, before any SQL is written.",
     size=9.6, color=DIM, ls=1.0)

# three graph-only wins
for i, (t, b, c) in enumerate([
    ("Fan-out warning", "Cardinality on the edge flags double-counting risk.", WARN),
    ("Self-joins found", "manager_id → employee_id would otherwise be missed.", KG),
    ("Honest refusal", "No path between domains → say so, never fabricate one.", TEAL),
]):
    x, w = cols(3)[i]
    y = 5.20
    rect(s, x, y, w, 1.06, fill=SURFACE, line=BORDER)
    rect(s, x, y, 0.05, 1.06, fill=c, line=None)
    text(s, x + 0.26, y + 0.18, w - 0.50, 0.24, t, size=11.2, color=TEXT, bold=True, ls=1.0)
    text(s, x + 0.26, y + 0.50, w - 0.50, 0.44, b, size=9.4, color=DIM, ls=1.20)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 14 — System block diagram (six layers)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "System Architecture", "Six layers, one process")

LX, LW = M, 1.46
BXX = M + LW + 0.18
BXW = CW - LW - 0.18
BH2, BG2 = 0.68, 0.135
BY2 = 1.56

bands6 = [
    ("Interface", ACCENT, [("Browser UI", "vanilla JS"), ("Live trace", "step by step"),
                           ("Quality panel", "dataset profile")]),
    ("API", ACCENT, [("/api/query", "ask"), ("/api/health", "status"),
                     ("/api/domains", "catalogue"), ("/api/quality", "profile")]),
    ("Reasoning", ACCENT, [("ReAct loop", "≤ 6 steps"), ("LLaMA-3.3-70B", "on Groq"),
                           ("Grounding", "figures vs rows")]),
    ("Tools", KG, [("get_schema_context", "→ graph"), ("sample_values", "→ database"),
                   ("run_sql", "→ database, read-only")]),
    ("Stores", KG, [("Neo4j", "441 nodes · 3 vector indexes"),
                    ("MiniLM 384-d", "local embeddings"),
                    ("SQLite", "23,293 rows")]),
    ("Catalogue", SQL, [("schema.json", "the contract"), ("datagen", "seeded CSVs"),
                        ("quality gate", "integrity"), ("loader", "→ both stores")]),
]
for bi, (layer, lc, blocks) in enumerate(bands6):
    by = BY2 + bi * (BH2 + BG2)
    rect(s, LX, by, LW, BH2, fill=SURFACE2, line=BORDER)
    rect(s, LX, by, 0.05, BH2, fill=lc, line=None)
    text(s, LX + 0.18, by, LW - 0.32, BH2,
         [[(f"L{6 - bi}", {"color": MUTED, "size": 7.8}),
           ("  " + layer, {"color": lc, "size": 10.2, "bold": True})]],
         ls=1.08, anchor=MSO_ANCHOR.MIDDLE)
    for i, (t, sub) in enumerate(cols(len(blocks), gap=0.14, x0=BXX, total=BXW) and blocks):
        x, w = cols(len(blocks), gap=0.14, x0=BXX, total=BXW)[i]
        rect(s, x, by, w, BH2, fill=SURFACE, line=BORDER)
        rect(s, x, by, w, 0.04, fill=lc, line=None)
        mono = t.startswith("/") or "_" in t or "." in t
        text(s, x + 0.18, by + 0.16, w - 0.34, 0.22, t, size=10.2, color=TEXT, bold=True,
             font=MONO if mono else SANS, ls=1.0)
        text(s, x + 0.18, by + 0.41, w - 0.34, 0.20, sub, size=8.2, color=MUTED, ls=1.0)
    if bi < 5:
        arrow(s, BXX + 0.40, by + BH2 + 0.008, 0.12, 0.115, MSO_SHAPE.DOWN_ARROW, BORDER_HI)

text(s, BXX, BY2 + 6 * (BH2 + BG2) + 0.02, BXW, 0.22,
     [[("Request flows down, answer returns up. ", {"color": DIM, "size": 9.4}),
       ("One FastAPI process serves every layer above the stores.",
        {"color": ACCENT_TX, "size": 9.4, "bold": True})]], ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 15 — DIVIDER: the proof
# ═══════════════════════════════════════════════════════════════════════════
divider("Section three", "The Proof", "Measured on this repository — not estimated.", "03")

# ═══════════════════════════════════════════════════════════════════════════
# 16 — Context economy  (hero bars)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Result 01  ·  Efficiency", "The graph makes the model's job smaller")

hero(s, M, 1.72, 4.10, "83.8%", "of prompt context removed", ACCENT_TX, vsize=62)
rect(s, M + 0.70, 2.98, 2.70, 0.014, fill=ACCENT, line=None)
ctext(s, M, 3.22, 4.10, 0.66,
      [[("6.2× smaller payload", {"color": TEXT, "bold": True, "size": 15})],
       [("on every one of up to 6 model calls", {"color": MUTED, "size": 10.4})]], ls=1.30)

BX2 = 5.30
BW2 = SW - M - BX2
BAR_MAX = BW2 - 1.90
for i, (lab, sub, tok, frac, c) in enumerate([
    ("Whole catalogue in the prompt", "50 tables · 373 columns", "10,224", 1.0, ERR),
    ("Graph-retrieved slice", "8 tables · ~59 columns", "1,655", 1655 / 10224, TEAL),
]):
    y = 1.80 + i * 1.20
    text(s, BX2, y, BAR_MAX, 0.24, lab, size=11.4, color=TEXT, bold=True, ls=1.0)
    text(s, BX2, y + 0.26, BAR_MAX, 0.20, sub, size=8.8, color=MUTED, ls=1.0)
    rect(s, BX2, y + 0.54, BAR_MAX, 0.34, fill=SURFACE2, line=None)
    rect(s, BX2, y + 0.54, max(BAR_MAX * frac, 0.12), 0.34, fill=c, line=None)
    text(s, BX2 + BAR_MAX + 0.18, y + 0.52, 1.70, 0.30,
         [[(tok, {"size": 16, "color": TEXT, "bold": True}),
           (" tok", {"size": 9, "color": MUTED})]], ls=1.0)
text(s, BX2, 4.24, BW2, 0.20, "token estimate = characters ÷ 4", size=8.4, color=MUTED, ls=1.0)

wins = [("Sharper", "fewer ways to be plausibly wrong", ACCENT),
        ("Faster", "a smaller prompt is a faster answer", SQL),
        ("Cheaper", "token spend falls with the payload", TEAL),
        ("Scalable", "flat at 50 tables or 5,000", WARN)]
for i, (t, b, c) in enumerate(wins):
    x, w = cols(4)[i]
    y = 4.86
    rect(s, x, y, w, 1.12, fill=SURFACE, line=BORDER)
    rect(s, x, y, w, 0.05, fill=c, line=None)
    text(s, x + 0.26, y + 0.24, w - 0.50, 0.28, t, size=13.5, color=c, bold=True, ls=1.0)
    text(s, x + 0.26, y + 0.60, w - 0.50, 0.40, b, size=9.8, color=DIM, ls=1.18)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 17 — Trust stack
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Result 02  ·  Trust", "Four guards, none of which trusts the model")

layers = [("The trace", "every tool call, every correction, returned with the answer", ACCENT, T4),
          ("The grounding check", "stated figures matched against the returned rows", TEAL, T3),
          ("Honest success", "true only when a conclusive answer actually ran SQL", SQL, T2),
          ("Graceful failure", "a classified message, never a stack trace", WARN, T1)]
LY, LH, LG = 1.62, 0.82, 0.16
for i, (t, b, c, band) in enumerate(layers):
    y = LY + i * (LH + LG)
    inset = i * 0.40
    x = M + inset
    w = CW - inset * 2
    rect(s, x, y, w, LH, fill=band, line=None)
    rect(s, x, y, 0.06, LH, fill=c, line=None)
    text(s, x + 0.34, y + 0.14, 3.20, 0.28, t, size=13.5,
         color=WHITE if i < 2 else TEXT, bold=True, ls=1.0)
    text(s, x + 0.34, y + 0.46, w - 0.70, 0.24, b, size=10.2,
         color=WHITE if i < 2 else DIM, ls=1.0)
    rect(s, x + w - 0.96, y + 0.24, 0.62, 0.34, fill=WHITE if i < 2 else ACCENT, line=None)
    label_in(s, x + w - 0.96, y + 0.24, 0.62, 0.34, f"0{i+1}", size=10,
             color=c if i < 2 else WHITE)

ey2 = LY + 3 * (LH + LG) + LH + 0.22
rect(s, M, ey2, CW, 0.94, fill=SURFACE, line=ACCENT, lw=1.4)
rect(s, M, ey2, 0.055, 0.94, fill=ACCENT, line=None)
text(s, M + 0.32, ey2 + 0.16, CW - 0.72, 0.28,
     "Grounding advises, it never blocks.", size=13.5, color=TEXT, bold=True, ls=1.0)
text(s, M + 0.32, ey2 + 0.52, CW - 0.72, 0.24,
     "Derived figures like “4.06 orders per customer” appear in no single cell — so a hard gate "
     "would reject correct answers.", size=10.4, color=MUTED, ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 18 — Live trace  (waterfall)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "Result 03  ·  Evidence", "One question, and everything it left behind")

rect(s, M, 1.62, CW, 0.70, fill=SURFACE2, line=ACCENT, lw=1.4)
rect(s, M, 1.62, 0.055, 0.70, fill=ACCENT, line=None)
text(s, M + 0.32, 1.74, 1.10, 0.24, "ASKED", size=8.4, color=ACCENT_TX, bold=True, spc=1.2, ls=1.0)
text(s, M + 1.44, 1.76, CW - 1.80, 0.34, "“What was total revenue by region last quarter?”",
     size=16, color=TEXT, bold=True, ls=1.0)

steps = [("get_schema_context", "the graph returns 4 tables, 3 join keys, 1 metric", 0.0, 2.30, KG),
         ("sample_values", "6 real region names, so the filter is not guessed", 2.30, 1.10, SQL),
         ("run_sql", "the SELECT executes read-only and returns 6 rows", 3.40, 3.10, SQL),
         ("grounding", "every stated figure found in those rows", 6.50, 1.10, TEAL)]
TOTAL = 7.60
TRX, TRW = M + 2.36, CW - 2.36 - 2.10
for i, (tool, obs, start, dur, c) in enumerate(steps):
    y = 2.60 + i * 0.86
    text(s, M, y + 0.06, 2.20, 0.22, tool, size=10, color=c, bold=True, font=MONO, ls=1.0)
    text(s, M, y + 0.28, 2.24, 0.36, obs, size=8.4, color=MUTED, ls=1.12)
    rect(s, TRX, y + 0.06, TRW, 0.30, fill=SURFACE, line=None)
    bx2 = TRX + TRW * (start / TOTAL)
    bw3 = max(TRW * (dur / TOTAL), 0.16)
    rect(s, bx2, y + 0.06, bw3, 0.30, fill=c, line=None)
    text(s, TRX + TRW + 0.16, y + 0.06, 1.90, 0.30,
         [[(f"{dur:.1f}", {"size": 12, "color": TEXT, "bold": True}),
           (" s", {"size": 8.6, "color": MUTED})]], ls=1.0)
rect(s, TRX, 6.06, TRW, 0.006, fill=BORDER, line=None)
text(s, TRX, 6.14, TRW, 0.22, "elapsed  →   0 s                                          "
     "                             7.6 s", size=8, color=MUTED, font=MONO, ls=1.0)

ctext(s, M, 6.50, CW, 0.28,
      [[("Answer, SQL, rows, trace and a grounded badge — ", {"color": DIM, "size": 12.5}),
        ("all four returned together, every time.", {"color": ACCENT_TX, "bold": True, "size": 12.5})]],
      ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 19 — Tools constellation
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "The Stack", "Every tool, and the job it does")

groups = [
    ("Graph", KG, ["Neo4j AuraDB", "neo4j driver 6.0.2", "Cypher", "native vector indexes"]),
    ("Model", ACCENT_TX, ["Groq API", "LLaMA-3.3-70B", "groq SDK 1.5.0", "ReAct loop (ours)"]),
    ("Retrieval", SQL, ["sentence-transformers", "all-MiniLM-L6-v2", "384-d cosine", "shortestPath"]),
    ("Backend", ACCENT_TX, ["FastAPI 0.115.9", "Uvicorn 0.34.3", "Pydantic", "python-dotenv"]),
    ("Data", SQL, ["SQLite 3", "pandas 2.3.0", "Faker (seed 42)", "schema validator"]),
    ("Delivery", TEAL, ["Vanilla JS + CSS", "pytest · 184 tests", "Railway", "GitHub"]),
]
GH2 = 2.24
for gi, (name, c, items) in enumerate(groups):
    x, w = cols(3, gap=0.26)[gi % 3]
    y = 1.62 + (gi // 3) * (GH2 + 0.26)
    rect(s, x, y, w, GH2, fill=SURFACE, line=BORDER)
    rect(s, x, y, w, 0.05, fill=c, line=None)
    text(s, x + 0.28, y + 0.24, w - 0.56, 0.32, name, size=16, color=c, bold=True, ls=1.0)
    rect(s, x + 0.28, y + 0.64, w - 0.56, 0.006, fill=BORDER, line=None)
    for ri, it in enumerate(items):
        ry = y + 0.80 + ri * 0.34
        rect(s, x + 0.28, ry + 0.09, 0.12, 0.12, fill=c, line=None, shape=MSO_SHAPE.OVAL)
        text(s, x + 0.52, ry + 0.02, w - 0.80, 0.24, it, size=10, color=DIM, ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 20 — Impact  (before / after)
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "What Changes", "For the business, and for the data team")

pairs = [("Getting a number", "File a ticket. Wait.", "Ask. Read the answer."),
         ("The analyst's day", "Writing routine joins.", "Curating the catalogue."),
         ("“Revenue”", "Depends who you ask.", "One governed expression."),
         ("Confidence", "Trust the spreadsheet.", "Read the SQL and the trace.")]
CY2, RH, RG = 1.62, 0.84, 0.12
text(s, M + 2.70, CY2, 4.10, 0.24, "BEFORE", size=8.8, color=ERR, bold=True, spc=1.3, ls=1.0)
text(s, M + 7.30, CY2, 4.10, 0.24, "NOW", size=8.8, color=TEAL, bold=True, spc=1.3, ls=1.0)
for i, (topic, before, after) in enumerate(pairs):
    y = CY2 + 0.32 + i * (RH + RG)
    text(s, M, y + 0.26, 2.50, 0.30, topic, size=11.6, color=TEXT, bold=True, ls=1.10)
    rect(s, M + 2.70, y, 4.10, RH, fill=SURFACE, line=BORDER)
    text(s, M + 2.96, y + 0.27, 3.60, 0.30, before, size=11, color=MUTED, ls=1.0)
    arrow(s, M + 6.94, y + RH / 2 - 0.075, 0.26, 0.15, color=ACCENT)
    rect(s, M + 7.30, y, 4.10, RH, fill=PAPER, line=TEAL, lw=1.4)
    text(s, M + 7.56, y + 0.27, 3.60, 0.30, after, size=11, color=TEXT, bold=True, ls=1.0)

ey3 = CY2 + 0.32 + 3 * (RH + RG) + RH + 0.22
for i, (x, w) in enumerate(cols(4)):
    v, l, c = [("83.8%", "less prompt context", ACCENT_TX), ("6.2×", "smaller payload", SQL),
               ("441", "nodes serving the plan", KG), ("184", "tests on the loop", TEAL)][i]
    tile(s, x, ey3, w, 0.86, v, l, color=c, vsize=18)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 21 — TO DO  /  TO EXPLORE
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
header(s, "What's Next", "What we will build — and what we want to find out")

# ── TO DO (committed) ──
LWc = 5.95
rect(s, M, 1.62, LWc, 4.60, fill=SURFACE, line=BORDER)
rect(s, M, 1.62, LWc, 0.06, fill=TEAL, line=None)
text(s, M + 0.30, 1.84, LWc - 0.60, 0.30, "TO DO", size=15, color=TEAL, bold=True, spc=1.2, ls=1.0)
text(s, M + 0.30, 2.18, LWc - 0.60, 0.22, "Committed · next two quarters", size=9,
     color=MUTED, ls=1.0)
todo = [("Run the live accuracy baseline",
         "The harness exists; the number does not yet. This is the gate for everything else."),
        ("Point it at real warehouse metadata",
         "The architecture is catalogue-driven — a new domain needs no code change."),
        ("Harden the prompt against the eval",
         "A/B every change. On a 70B model, prompt edits regress as often as they help."),
        ("Row-level access control",
         "Today the agent reads everything. Production needs per-user scoping in the graph.")]
for i, (t, b) in enumerate(todo):
    y = 2.58 + i * 0.92
    rect(s, M + 0.30, y + 0.06, 0.24, 0.24, fill=TEAL, line=None)
    label_in(s, M + 0.30, y + 0.06, 0.24, 0.24, "✓", size=9.5, color=WHITE)
    text(s, M + 0.70, y, LWc - 1.06, 0.26, t, size=11.6, color=TEXT, bold=True, ls=1.0)
    text(s, M + 0.70, y + 0.30, LWc - 1.06, 0.48, b, size=9.4, color=DIM, ls=1.20)

# ── TO EXPLORE (open questions) ──
RXc = M + LWc + 0.36
RWc = SW - M - RXc
grad(s, RXc, 1.62, RWc, 4.60, RGBColor(0xF7, 0xEF, 0xFE), RGBColor(0xEC, 0xDD, 0xFB), angle=90.0)
rect(s, RXc, 1.62, RWc, 0.06, fill=ACCENT, line=None)
text(s, RXc + 0.30, 1.84, RWc - 0.60, 0.30, "TO EXPLORE", size=15, color=ACCENT_TX,
     bold=True, spc=1.2, ls=1.0)
text(s, RXc + 0.30, 2.18, RWc - 0.60, 0.22, "Open questions · genuinely unproven", size=9,
     color=MUTED, ls=1.0)
explore = [("Can the graph hold facts, not just schema?",
            "Today it stores metadata. If it also stored derived facts, the agent could reason "
            "over answers instead of re-querying for them."),
           ("Should the agent write back what it learns?",
            "Every resolved question is a new alias, a new metric, a better description. A graph "
            "that improves each time it is used."),
           ("Where is the honest ceiling?",
            "Some questions are ambiguous to a human analyst too. We want the system to say so — "
            "and we do not yet know how often that is.")]
for i, (q, b) in enumerate(explore):
    y = 2.62 + i * 1.24
    rect(s, RXc + 0.30, y + 0.02, 0.24, 0.24, fill=ACCENT, line=None, shape=MSO_SHAPE.OVAL)
    label_in(s, RXc + 0.30, y + 0.02, 0.24, 0.24, "?", size=10, color=WHITE)
    text(s, RXc + 0.70, y - 0.04, RWc - 1.06, 0.30, q, size=11.6, color=ACCENT_TX,
         bold=True, ls=1.06)
    text(s, RXc + 0.70, y + 0.30, RWc - 1.06, 0.72, b, size=9.4, color=DIM, ls=1.24)

ctext(s, M, 6.42, CW, 0.26,
      [[("The left column is engineering. ", {"color": DIM, "size": 11.5}),
        ("The right column is where the interesting work is.",
         {"color": ACCENT_TX, "bold": True, "size": 11.5})]], ls=1.0)
footer(s)

# ═══════════════════════════════════════════════════════════════════════════
# 22 — Closing thought
# ═══════════════════════════════════════════════════════════════════════════
s = new_slide()
grad(s, 0, 0, SW, SH, ACCENT_DK, ACCENT, angle=315.0)

# faint node motif
for (nx, ny, r_) in [(10.30, 1.30, .18), (11.80, 1.95, .12), (9.70, 2.50, .12),
                     (11.10, 3.15, .16), (12.40, 2.70, .10)]:
    rect(s, nx, ny, r_, r_, fill=RGBColor(0xC9, 0x8A, 0xF5), line=None, shape=MSO_SHAPE.OVAL)
for a, b, c, d in [(10.39, 1.39, 11.86, 1.95), (10.39, 1.39, 9.76, 2.50),
                   (11.86, 2.01, 11.18, 3.15), (9.76, 2.56, 11.10, 3.21),
                   (11.86, 2.01, 12.45, 2.70)]:
    line(s, a, b, c, d, color=RGBColor(0x9E, 0x5C, 0xD8), w=1.1)

rect(s, M, 1.66, 0.055, 0.34, fill=RGBColor(0xC9, 0x8A, 0xF5), line=None)
eyebrow(s, M + 0.17, 1.70, "In one line", color=RGBColor(0xE4, 0xC6, 0xFC), w=6.0)

text(s, M, 2.24, 9.40, 2.00,
     [[("The model brings language.", {"color": RGBColor(0xE9, 0xD6, 0xFB)})],
      [("The graph brings structure.", {"color": WHITE, "bold": True})]],
     size=42, ls=1.22, font=LIGHT)

rect(s, M, 4.52, 4.60, 0.014, fill=RGBColor(0xC9, 0x8A, 0xF5), line=None)
text(s, M, 4.80, 10.60, 0.60,
     "Keeping those two responsibilities apart is the entire design — and the reason the answers hold up.",
     size=14, color=RGBColor(0xDD, 0xBC, 0xF8), ls=1.36)

for i, (x, w) in enumerate(cols(4, gap=0.22, total=10.60)):
    v, l = [("83.8%", "less context"), ("6.2×", "smaller payload"),
            ("441", "nodes planning"), ("184", "tests guarding")][i]
    rect(s, x, 5.72, w, 0.86, fill=RGBColor(0x5E, 0x00, 0x99), line=None)
    rect(s, x, 5.72, w, 0.04, fill=RGBColor(0xC9, 0x8A, 0xF5), line=None)
    ctext(s, x, 5.92, w, 0.30, v, size=17, color=WHITE, bold=True, ls=1.0)
    ctext(s, x, 6.26, w, 0.20, l.upper(), size=7.4, color=RGBColor(0xD3, 0xA8, 0xF7),
          bold=True, spc=0.9, ls=1.0)

text(s, M, 6.88, 10.6, 0.24, "DataPulse   ·   Live on Railway   ·   Thank you",
     size=10, color=RGBColor(0xC0, 0x92, 0xE8), spc=0.5)
_n[0] += 1

prs.save(OUT)
print("saved:", OUT, "| slides:", len(prs.slides._sldIdLst))
