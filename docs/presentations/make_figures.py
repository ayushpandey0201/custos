"""Render the two figures used in the review deck.

Rendered to PNG rather than drawn in PowerPoint so the numbers stay tied to what
the system actually produced: the drift chart below carries the values from a
real ``run_demo`` execution, not hand-typed approximations.

    python docs/presentations/make_figures.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "figures"
SCALE = 300  # px per inch; slides are placed at inch dimensions

# Palette — matches the dashboard, so the deck and the live demo read as one system.
INK = (13, 17, 23)
MUTED = (110, 122, 136)
LINE = (198, 206, 216)
PANEL = (244, 246, 249)
WHITE = (255, 255, 255)
ALLOW = (47, 138, 67)
REVIEW = (183, 128, 12)
BLOCK = (200, 48, 44)
ACCENT = (31, 92, 168)

FONT_DIR = Path("/System/Library/Fonts/Supplemental")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    path = FONT_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def box(draw, xy, fill=WHITE, outline=LINE, width=3, radius=14):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def centred(draw, text, cx, cy, f, fill=INK):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=f)
    draw.text((cx - (right - left) / 2, cy - (bottom - top) / 2 - top), text, font=f, fill=fill)


def arrow(draw, start, end, colour=MUTED, width=4, head=16):
    draw.line([start, end], fill=colour, width=width)
    x1, y1 = end
    x0, y0 = start
    if abs(x1 - x0) > abs(y1 - y0):  # horizontal
        d = 1 if x1 > x0 else -1
        draw.polygon(
            [(x1, y1), (x1 - d * head, y1 - head // 2), (x1 - d * head, y1 + head // 2)],
            fill=colour,
        )
    else:  # vertical
        d = 1 if y1 > y0 else -1
        draw.polygon(
            [(x1, y1), (x1 - head // 2, y1 - d * head), (x1 + head // 2, y1 - d * head)],
            fill=colour,
        )


# --------------------------------------------------------------- architecture


def architecture(width_in: float = 11.0, height_in: float = 3.4) -> Path:
    """Request path: agent → gateway → engines, with the offline worker beside it.

    Only glyphs present in Arial are used. "▸" and "★" render as tofu boxes,
    which on a projector looks like a broken file rather than a design choice.
    """
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_box = font(38, bold=True)
    f_sub = font(29)
    f_tiny = font(25)
    f_label = font(30, bold=True)

    # --- Band A: agent <-> gateway ------------------------------------------
    box(d, (60, 50, 700, 270), fill=PANEL)
    centred(d, "AI agent / service", 380, 128, f_box)
    centred(d, "@custos.guard(...)", 380, 192, f_sub, MUTED)

    box(d, (1180, 50, 3240, 270), fill=PANEL, outline=ACCENT, width=4)
    centred(d, "GATEWAY  —  data plane", 2210, 120, f_box, ACCENT)
    centred(d, "auth → Trust Engine → fuse → decide → audit", 2210, 190, f_sub, MUTED)

    arrow(d, (720, 122), (1160, 122), ACCENT)
    centred(d, "POST /v1/evaluate", 940, 86, f_tiny, ACCENT)
    arrow(d, (1160, 200), (720, 200), MUTED)
    centred(d, "ALLOW / REVIEW / BLOCK", 940, 238, f_tiny, MUTED)

    # --- Band B: worker beside the concurrent engine fan-out ----------------
    y0, y1 = 420, 660
    box(d, (60, y0, 1040, y1), fill=WHITE, outline=LINE, width=3)
    centred(d, "WORKER  —  offline", 550, y0 + 70, f_box)
    centred(d, "PSI + KS per feature, severity roll-up", 550, y0 + 145, f_tiny, MUTED)
    centred(d, "no statistics on the request path (ADR 0002)", 550, y0 + 195, f_tiny, MUTED)

    engines = [
        ("Policy", "rules · veto", 1180, ALLOW),
        ("Drift", "PSI · KS · the core", 1890, ACCENT),
        ("Risk", "future seam", 2600, MUTED),
    ]
    for label, sub, x0, colour in engines:
        box(d, (x0, y0, x0 + 640, y1), fill=WHITE, outline=colour, width=4)
        centred(d, label, x0 + 320, y0 + 80, f_box, colour)
        centred(d, sub, x0 + 320, y0 + 152, f_tiny, MUTED)
        arrow(d, (x0 + 320, 280), (x0 + 320, y0 - 12), LINE, width=3)

    centred(d, "concurrent fan-out · 20 ms per-engine timeout", 2210, 350, f_tiny, MUTED)

    # --- Band C: shared storage and the cold control plane ------------------
    y2, y3 = 790, 990
    box(d, (1180, y2, 2160, y3), fill=PANEL)
    centred(d, "Cache  ·  Postgres", 1670, y2 + 68, f_label)
    centred(d, "severity · rules · config · audit chain", 1670, y2 + 130, f_tiny, MUTED)

    box(d, (2280, y2, 3240, y3), fill=PANEL)
    centred(d, "CONTROL PLANE", 2760, y2 + 68, f_label)
    centred(d, "register · configure · verify · export", 2760, y2 + 130, f_tiny, MUTED)

    # Worker writes severity; the drift engine reads it back. Two arrows,
    # because the separation between that write and that read is the whole of
    # ADR 0002 — and the read arrow lands on Drift specifically, since the
    # precomputed severity is what it consumes.
    #
    # The worker sits a band above the store, so its arrow is routed as an
    # elbow rather than drawn floating between two unconnected edges.
    d.line([(550, y1 + 4), (550, y2 + 100)], fill=MUTED, width=4)
    arrow(d, (550, y2 + 100), (1160, y2 + 100), MUTED)
    centred(d, "writes severity", 860, y2 + 62, f_tiny, MUTED)

    drift_cx, elbow_x, elbow_y = 1890 + 320, 2000, (y1 + y2) / 2
    d.line([(elbow_x, y2 - 4), (elbow_x, elbow_y)], fill=MUTED, width=4)
    d.line([(elbow_x, elbow_y), (drift_cx, elbow_y)], fill=MUTED, width=4)
    arrow(d, (drift_cx, elbow_y), (drift_cx, y1 + 12), MUTED)
    centred(d, "cached read", drift_cx + 200, elbow_y - 38, f_tiny, MUTED)

    path = OUT / "architecture.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


# ---------------------------------------------------------------- drift chart

# Values produced by an actual `python -m examples.fintech_demo.run_demo`.
DEMO_FEATURES = [
    ("utilisation", 0.500, "significant"),
    ("income", 0.350, "significant"),
    ("months_employed", 0.162, "moderate"),
    ("bureau_score", 0.010, "stable"),
]
BAND_COLOUR = {"stable": ALLOW, "moderate": REVIEW, "significant": BLOCK}


def drift_chart(width_in: float = 11.0, height_in: float = 3.15) -> Path:
    """Per-feature PSI after the population shift, against the industry bands."""
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_title = font(40, bold=True)
    f_label = font(34, bold=True)
    f_val = font(32, bold=True)
    f_tiny = font(26)

    d.text((60, 40), "Per-feature PSI after the population shift", font=f_title, fill=INK)
    d.text(
        (60, 105),
        "model severity 0.021 → 0.830   ·   verdict ALLOW → REVIEW",
        font=f_tiny,
        fill=MUTED,
    )

    left, right = 700, W - 420
    top, row_h = 210, 175
    x_max = 0.55  # a little past the 0.50 saturation point

    def x_of(psi: float) -> float:
        return left + (psi / x_max) * (right - left)

    # Band guides first, so bars sit on top of them. They stop at the last bar
    # rather than running to the floor — a rule extending past the data reads
    # as an axis the chart does not have.
    guide_bottom = top + row_h * (len(DEMO_FEATURES) - 1) + 96
    for threshold, label in ((0.10, "0.10  stable"), (0.25, "0.25  significant")):
        x = x_of(threshold)
        d.line([(x, top - 30), (x, guide_bottom)], fill=LINE, width=3)
        d.text((x + 12, top - 62), label, font=f_tiny, fill=MUTED)

    for i, (name, psi, band) in enumerate(DEMO_FEATURES):
        y = top + i * row_h
        colour = BAND_COLOUR[band]

        d.text((60, y + 22), name, font=f_label, fill=INK)
        d.rounded_rectangle(
            [(left, y + 14), (max(x_of(psi), left + 8), y + 84)], radius=8, fill=colour
        )
        d.text((x_of(psi) + 24, y + 24), f"{psi:.3f}", font=f_val, fill=colour)
        d.text((x_of(psi) + 190, y + 30), band, font=f_tiny, fill=MUTED)

    d.text(
        (60, H - 78),
        "bureau_score did not move and is not blamed — attribution is what separates "
        "a population shift from a broken pipeline",
        font=f_tiny,
        fill=MUTED,
    )

    path = OUT / "drift_attribution.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (architecture(), drift_chart()):
        print(f"wrote {path.relative_to(Path.cwd()) if path.is_absolute() else path}")


if __name__ == "__main__":
    main()
