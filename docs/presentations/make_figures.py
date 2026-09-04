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


# --------------------------------------------------------------- request flow


def dashed_v(draw, x, y0, y1, colour=LINE, width=3, dash=18, gap=14):
    """Vertical dashed line — PIL has no dash support."""
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + dash, y1))], fill=colour, width=width)
        y += dash + gap


def request_flow(width_in: float = 11.0, height_in: float = 4.15) -> Path:
    """Sequence of one /v1/evaluate call, in the order it actually happens.

    A sequence diagram rather than a component diagram: the question this
    answers is "what happens, in what order, and what does it cost" — which a
    box-and-arrow architecture picture cannot show.
    """
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_lane = font(28, bold=True)
    f_msg = font(25)
    f_num = font(23, bold=True)
    f_note = font(22)

    # Rightmost centre is 3010 so the 500px-wide lane header still clears the
    # 3300px canvas edge — an earlier layout clipped the Postgres box.
    lanes = [
        ("Agent", 300, INK),
        ("Gateway", 1000, ACCENT),
        ("Cache", 1700, MUTED),
        ("Engines", 2380, ALLOW),
        ("Postgres", 3010, MUTED),
    ]
    top, bottom = 60, H - 50
    for label, x, colour in lanes:
        box(d, (x - 250, top, x + 250, top + 110), fill=PANEL, outline=colour, width=3)
        centred(d, label, x, top + 55, f_lane, colour)
        dashed_v(d, x, top + 130, bottom)

    lane = {label: x for label, x, _ in lanes}
    y = top + 205
    step_h = 96

    def message(n, src, dst, text, note="", colour=MUTED, dashed=False):
        nonlocal y
        x0, x1 = lane[src], lane[dst]
        centred(d, str(n), 62, y, f_num, ACCENT)
        if dashed:
            # Return arrows are drawn lighter so the outbound path reads first.
            d.line([(x0, y), (x1, y)], fill=colour, width=3)
            head = 16
            dirn = 1 if x1 > x0 else -1
            d.polygon(
                [(x1, y), (x1 - dirn * head, y - head // 2), (x1 - dirn * head, y + head // 2)],
                fill=colour,
            )
        else:
            arrow(d, (x0, y), (x1, y), colour)
        centred(d, text, (x0 + x1) / 2, y - 30, f_msg, INK)
        if note:
            centred(d, note, (x0 + x1) / 2, y + 30, f_note, MUTED)
        y += step_h

    message(1, "Agent", "Gateway", "POST /v1/evaluate", "@custos.guard(...)", ACCENT)
    message(2, "Gateway", "Cache", "API key -> tenant_id", "SHA-256 digest, 60 s TTL")
    message(3, "Gateway", "Cache", "config + is model registered?", "30 s / 10 s TTL")
    message(4, "Gateway", "Engines", "fan out concurrently", "20 ms per-engine cap", ALLOW)
    message(5, "Engines", "Cache", "drift severity, policy rules", "precomputed reads (ADR 0002)")
    message(
        6, "Engines", "Gateway", "3 x SignalResult", "degraded engines excluded", ALLOW, dashed=True
    )

    # Step 7 happens inside the gateway, so it is drawn as a self-note rather
    # than a message between lifelines.
    gx = lane["Gateway"]
    centred(d, "7", 62, y, f_num, ACCENT)
    box(d, (gx - 250, y - 34, gx + 430, y + 34), fill=PANEL, outline=ACCENT, width=3)
    centred(d, "fuse -> decision matrix", gx + 90, y, f_msg, ACCENT)
    centred(d, "pure functions, no I/O", gx + 90, y + 56, f_note, MUTED)
    y += step_h + 20

    message(8, "Gateway", "Postgres", "append audit entry", "SHA-256 link to previous")
    message(
        9,
        "Gateway",
        "Agent",
        "ALLOW / REVIEW / BLOCK",
        "+ score, reasons, trace_id",
        ACCENT,
        dashed=True,
    )
    message(10, "Gateway", "Postgres", "store feature vector", "background - off the response path")

    path = OUT / "request_flow.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


# -------------------------------------------------------------- decision flow


def decision_flow(width_in: float = 11.0, height_in: float = 2.75) -> Path:
    """The decision matrix as the ordered cascade it actually is.

    Drawn left to right with each condition dropping to its verdict, because
    the *order* is the specification: rule 2 precedes rule 3 so that an
    unregistered model with damning signals is blocked, not merely flagged.
    """
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_cond = font(26, bold=True)
    f_small = font(21)
    f_verdict = font(27, bold=True)
    f_edge = font(20, bold=True)

    steps = [
        (["any veto?"], "", BLOCK, "BLOCK"),
        (["trust < 0.30?"], "block threshold", BLOCK, "BLOCK"),
        (["model", "unregistered?"], "ADR 0005", REVIEW, "REVIEW"),
        (["all engines", "degraded?"], "no signal at all", REVIEW, "REVIEW"),
        (["trust < 0.60?"], "review threshold", REVIEW, "REVIEW"),
    ]

    # Widths chosen so the trailing ALLOW terminal still lands inside the
    # canvas: 70 + 4*(box_w + gap) + box_w + gap + 250 must stay under 3300.
    x0, box_w, gap = 70, 490, 70
    cy, cond_h = 230, 190
    verdict_y = 570

    for i, (lines, sub, colour, verdict) in enumerate(steps):
        left = x0 + i * (box_w + gap)
        box(d, (left, cy - cond_h // 2, left + box_w, cy + cond_h // 2), fill=PANEL, width=3)
        cx = left + box_w // 2

        start = cy - 22 if sub else cy - (len(lines) - 1) * 17
        for j, line in enumerate(lines):
            centred(d, line, cx, start + j * 34, f_cond)
        if sub:
            centred(d, sub, cx, cy + 46, f_small, MUTED)

        # "yes" drops to the verdict; "no" continues right to the next test.
        arrow(d, (cx, cy + cond_h // 2), (cx, verdict_y - 46), colour, width=4)
        centred(d, "yes", cx + 62, cy + cond_h // 2 + 44, f_edge, colour)

        box(
            d,
            (cx - 130, verdict_y - 44, cx + 130, verdict_y + 44),
            fill=WHITE,
            outline=colour,
            width=4,
        )
        centred(d, verdict, cx, verdict_y, f_verdict, colour)

        nxt = left + box_w
        if i < len(steps) - 1:
            arrow(d, (nxt, cy), (nxt + gap, cy), MUTED, width=4)
            centred(d, "no", nxt + gap // 2, cy - 34, f_edge, MUTED)

    # Falling off the end of the cascade is the only way to reach ALLOW.
    last = x0 + (len(steps) - 1) * (box_w + gap) + box_w
    arrow(d, (last, cy), (last + gap, cy), ALLOW, width=4)
    centred(d, "no", last + gap // 2, cy - 34, f_edge, ALLOW)
    box(d, (last + gap, cy - 52, last + gap + 250, cy + 52), fill=WHITE, outline=ALLOW, width=4)
    centred(d, "ALLOW", last + gap + 125, cy, f_verdict, ALLOW)

    centred(
        d,
        "Evaluated top to bottom in this order. Rule 2 precedes rule 3 deliberately: an "
        "unregistered model whose signals are already damning is blocked, not merely flagged.",
        W // 2,
        H - 55,
        f_small,
        MUTED,
    )

    path = OUT / "decision_flow.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


# -------------------------------------------------------------- drift pipeline


def drift_pipeline(width_in: float = 11.0, height_in: float = 2.8) -> Path:
    """Where the drift statistics run, and where they do not.

    The dashed boundary is the point of ADR 0002: everything expensive happens
    below it, on a schedule, and the request path above it only ever reads.
    """
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_band = font(27, bold=True)
    f_box = font(28, bold=True)
    f_sub = font(23)
    f_note = font(22)

    def stage(x0, y0, x1, y1, title, sub, colour=LINE, fill=WHITE):
        box(d, (x0, y0, x1, y1), fill=fill, outline=colour, width=3)
        cx = (x0 + x1) // 2
        centred(d, title, cx, y0 + 58, f_box, INK if colour is LINE else colour)
        for i, line in enumerate(sub):
            centred(d, line, cx, y0 + 112 + i * 40, f_sub, MUTED)

    # --- online band ---------------------------------------------------
    centred(d, "ON THE REQUEST PATH   —   one cached read", 690, 60, f_band, ACCENT)
    stage(70, 110, 800, 300, "Gateway", ["/v1/evaluate"], ACCENT, PANEL)
    stage(900, 110, 1700, 300, "DriftEngine", ["trust = 1 - severity"], ACCENT)
    stage(1800, 110, 2600, 300, "Cache", ["severity, 15 s TTL"], MUTED, PANEL)
    stage(2700, 110, 3230, 300, "Verdict", ["+ top features"], ACCENT)

    arrow(d, (810, 205), (890, 205), ACCENT)
    arrow(d, (1710, 205), (1790, 205), ACCENT)
    arrow(d, (1795, 250), (1715, 250), MUTED)
    arrow(d, (2610, 205), (2690, 205), ACCENT)

    # --- the boundary --------------------------------------------------
    y_line = 400
    x = 70
    while x < W - 70:
        d.line([(x, y_line), (min(x + 26, W - 70), y_line)], fill=BLOCK, width=4)
        x += 44
    centred(
        d,
        "ADR 0002  —  nothing below this line runs on the request path",
        W // 2,
        y_line - 44,
        f_note,
        BLOCK,
    )

    # --- offline band --------------------------------------------------
    centred(d, "OFFLINE   —   Celery worker, hourly or on demand", 780, 470, f_band, MUTED)
    y0, y1 = 520, 730
    stage(
        70,
        y0,
        720,
        y1,
        "feature_samples",
        ["captured per request,", "in the background"],
        MUTED,
        PANEL,
    )
    stage(800, y0, 1500, y1, "Worker", ["window vs. baseline", "fixed at registration"])
    stage(1580, y0, 2280, y1, "PSI + KS", ["per feature,", "pure stdlib Python"])
    stage(2360, y0, 3230, y1, "Severity roll-up", ["0.6 x max + 0.4 x mean", "-> drift_snapshots"])

    for x0, x1 in ((730, 790), (1510, 1570), (2290, 2350)):
        arrow(d, (x0, (y0 + y1) // 2), (x1, (y0 + y1) // 2), MUTED)

    # The write that closes the loop back to the hot path. It deliberately
    # crosses the ADR 0002 boundary: that crossing *is* the contract — the
    # worker writes a snapshot, and the request path only ever reads it.
    up_x, turn_y, into_x = 2795, 445, 2200
    d.line([(up_x, y0 - 10), (up_x, turn_y)], fill=ALLOW, width=4)
    d.line([(up_x, turn_y), (into_x, turn_y)], fill=ALLOW, width=4)
    arrow(d, (into_x, turn_y), (into_x, 310), ALLOW, width=4)
    # Below the elbow, not above it — above collides with the ADR 0002 rule.
    centred(d, "writes snapshot, evicts the cache", up_x - 210, turn_y + 38, f_note, ALLOW)

    path = OUT / "drift_pipeline.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (architecture(), request_flow(), decision_flow(), drift_pipeline(), drift_chart()):
        print(f"wrote {path.relative_to(Path.cwd()) if path.is_absolute() else path}")


if __name__ == "__main__":
    main()
