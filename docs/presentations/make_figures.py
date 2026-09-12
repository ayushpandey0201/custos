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


# ----------------------------------------------------------- calibration curve

# Produced by running engines/drift/detectors.py over the demo's `income`
# feature (mu 60000, sigma 15000), shifting the mean by a KNOWN number of
# standard deviations and recording what PSI reports back. 600 samples per
# side, 15 trials per point; the band is the min-max across those trials.
#
# This is the whole validation argument in one table: the input is chosen, so
# the correct output is known, so the reading can actually be checked.
CALIBRATION = [
    # shift (sigma), PSI mean, PSI min, PSI max, KS mean, band
    (0.00, 0.030, 0.012, 0.070, 0.053, "stable"),
    (0.25, 0.104, 0.046, 0.181, 0.134, "moderate"),
    (0.50, 0.287, 0.162, 0.403, 0.227, "significant"),
    (0.75, 0.591, 0.389, 0.755, 0.320, "significant"),
    (1.00, 1.019, 0.764, 1.239, 0.411, "significant"),
    (1.50, 2.203, 1.728, 2.891, 0.570, "significant"),
    (2.00, 4.214, 2.890, 5.016, 0.699, "significant"),
]


def calibration_curve(width_in: float = 11.0, height_in: float = 3.45) -> Path:
    """Measured PSI against a shift of known size — the instrument in ice and steam.

    The y axis is logarithmic because the two thresholds that decide a verdict,
    0.10 and 0.25, sit in the bottom twentieth of a linear axis that has to
    reach 4.2. On a linear scale the most important part of this chart is a
    smudge above the baseline.
    """
    import math

    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_title = font(40, bold=True)
    f_sub = font(26)
    f_val = font(26, bold=True)
    f_tick = font(24)
    f_axis = font(27, bold=True)
    f_note = font(25, bold=True)

    d.text((60, 36), "Calibration — what the detector reports for a shift we chose",
           font=f_title, fill=INK)
    d.text((60, 98),
           "income feature, mean moved by a known number of standard deviations   ·   "
           "600 samples/side, 15 trials/point",
           font=f_sub, fill=MUTED)

    left, right = 250, W - 640
    top, bottom = 205, H - 190
    y_min, y_max = 0.01, 6.0
    log_min, log_max = math.log10(y_min), math.log10(y_max)
    x_max = 2.15

    def y_of(v: float) -> float:
        frac = (math.log10(max(v, y_min)) - log_min) / (log_max - log_min)
        return bottom - frac * (bottom - top)

    def x_of(s: float) -> float:
        return left + (s / x_max) * (right - left)

    # Industry bands as shaded regions — the thresholds a credit-risk team
    # already uses, so the reading means something before we explain it.
    for lo, hi, tint in (
        (y_min, 0.10, (233, 245, 235)),
        (0.10, 0.25, (252, 246, 230)),
        (0.25, y_max, (252, 235, 234)),
    ):
        d.rectangle([(left, y_of(hi)), (right, y_of(lo))], fill=tint)
    for thresh, label, colour in ((0.10, "0.10  stable", ALLOW),
                                  (0.25, "0.25  significant", BLOCK)):
        y = y_of(thresh)
        d.line([(left, y), (right, y)], fill=colour, width=3)
        d.text((right + 24, y - 18), label, font=f_tick, fill=colour)

    for decade in (0.01, 0.1, 1.0):
        y = y_of(decade)
        d.text((left - 170, y - 16), f"{decade:g}", font=f_tick, fill=MUTED)
    d.text((60, top - 8), "PSI", font=f_axis, fill=INK)

    # Spread bars first, then the mean markers on top.
    points = [(x_of(s), y_of(m)) for s, m, _, _, _, _ in CALIBRATION]
    d.line(points, fill=ACCENT, width=5)
    for (shift, mean, lo, hi, _ks, band) in CALIBRATION:
        x = x_of(shift)
        d.line([(x, y_of(lo)), (x, y_of(hi))], fill=ACCENT, width=3)
        d.ellipse([(x - 12, y_of(mean) - 12), (x + 12, y_of(mean) + 12)],
                  fill=BAND_COLOUR[band], outline=WHITE, width=3)
        centred(d, f"{shift:g}σ", x, bottom + 44, f_axis, fill=INK)
        if shift in (0.0, 1.0):
            centred(d, f"{mean:.3f}", x, y_of(mean) - 52, f_val, fill=BAND_COLOUR[band])

    # No x-axis caption: the subtitle already says what the axis is, and a
    # second label here collides with the footnote.

    # The two reference points the whole argument rests on.
    d.text((right + 24, top + 18), "Nothing moved", font=f_note, fill=ALLOW)
    d.text((right + 24, top + 58), "0σ reads 0.030 —", font=f_tick, fill=MUTED)
    d.text((right + 24, top + 92), "stable, not zero-drift", font=f_tick, fill=MUTED)
    d.text((right + 24, top + 148), "Known 1σ shift", font=f_note, fill=BLOCK)
    d.text((right + 24, top + 188), "reads 1.019 — 4× the", font=f_tick, fill=MUTED)
    d.text((right + 24, top + 222), "significant threshold", font=f_tick, fill=MUTED)

    d.text((60, H - 68),
           "Monotone across every step, and the bands are crossed where a credit-risk team "
           "expects them to be. On real data none of this could be checked — nobody knows the "
           "true drift in it.",
           font=f_sub, fill=MUTED)

    path = OUT / "calibration_curve.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


# --------------------------------------------------------------- load profile

# Produced by `python -m benchmarks.load_test --sweep 50,100,200,400,600,800
# --duration 15 --warmup 3` on an M1, SQLite, one uvicorn worker. Raw output in
# benchmarks/results-sqlite.json. Latencies are the coordinated-omission
# corrected response time, which is what the caller actually waits.
LOAD_PROFILE = [
    # offered, p99 ms, achieved req/s
    (50, 10.71, 50.0),
    (100, 49.32, 100.0),
    (200, 93.66, 200.0),
    (400, 66390.0, 74.0),
    (600, 99408.0, 78.3),
    (800, 149597.0, 72.5),
]
BUDGET_MS = 50.0


def load_profile(width_in: float = 11.0, height_in: float = 3.3) -> Path:
    """p99 latency against offered rate, on a log axis, with the budget drawn in.

    Log scale because the data spans four orders of magnitude — 10 ms to 150 s.
    A linear axis would render every passing rate as an invisible sliver at the
    baseline and turn the one genuinely interesting region, the crossing of the
    budget line, into nothing.
    """
    import math

    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_title = font(40, bold=True)
    f_sub = font(26)
    f_val = font(27, bold=True)
    f_tick = font(24)
    f_axis = font(26, bold=True)

    d.text((60, 36), "Gateway under load — where the 50 ms budget stops holding",
           font=f_title, fill=INK)
    d.text((60, 98),
           "open-loop generator, latency measured from scheduled send time   ·   "
           "M1, SQLite, 1 worker",
           font=f_sub, fill=MUTED)

    left, right = 210, W - 330
    top, bottom = 200, H - 175
    y_min, y_max = 5.0, 300_000.0
    log_min, log_max = math.log10(y_min), math.log10(y_max)

    def y_of(ms: float) -> float:
        frac = (math.log10(ms) - log_min) / (log_max - log_min)
        return bottom - frac * (bottom - top)

    # Decade gridlines, drawn first so bars cover them.
    for decade, label in ((10, "10 ms"), (100, "100 ms"), (1000, "1 s"),
                          (10_000, "10 s"), (100_000, "100 s")):
        y = y_of(decade)
        d.line([(left, y), (right, y)], fill=LINE, width=2)
        d.text((left - 150, y - 16), label, font=f_tick, fill=MUTED)

    slot = (right - left) / len(LOAD_PROFILE)
    bar_w = slot * 0.46

    for i, (offered, p99, achieved) in enumerate(LOAD_PROFILE):
        cx = left + slot * (i + 0.5)
        passed = p99 <= BUDGET_MS
        colour = ALLOW if passed else BLOCK
        y = y_of(p99)
        d.rounded_rectangle([(cx - bar_w / 2, y), (cx + bar_w / 2, bottom)],
                            radius=8, fill=colour)

        shown = f"{p99:.0f} ms" if p99 < 1000 else f"{p99 / 1000:.0f} s"
        centred(d, shown, cx, y - 34, f_val, fill=colour)
        centred(d, f"{offered}/s", cx, bottom + 40, f_axis, fill=INK)
        # Achieved throughput under the offered rate: the collapse is only
        # visible by comparing the two.
        centred(d, f"{achieved:.0f} served", cx, bottom + 86, f_tick,
                fill=MUTED if achieved >= offered * 0.95 else BLOCK)

    # Budget line last, on top of everything, because it is the whole point.
    y_budget = y_of(BUDGET_MS)
    # Stop the rule short of its own label, or the dashes run through the text.
    dashed_h(d, y_budget, left - 40, right + 20, colour=BLOCK, width=4)
    d.text((right + 46, y_budget - 56), "50 ms", font=f_val, fill=BLOCK)
    d.text((right + 46, y_budget + 14), "budget", font=f_tick, fill=BLOCK)

    d.text((60, H - 62),
           "Holds to 100 req/s per instance. Throughput survives 200 req/s; the latency "
           "budget does not. Past that, congestion collapse — more load, less served.",
           font=f_sub, fill=MUTED)

    path = OUT / "load_profile.png"
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


# ------------------------------------------------------------ problem framing


def dashed_h(draw, y, x0, x1, colour=LINE, width=3, dash=22, gap=16):
    """Horizontal dashed line — PIL has no dash support."""
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill=colour, width=width)
        x += dash + gap


def problem_timeline(width_in: float = 11.0, height_in: float = 2.75) -> Path:
    """The timing gap, drawn to scale.

    The single most important picture in the deck: monitoring is periodic,
    damage is continuous, and the span between the two is the problem this
    project exists to close. The red bar is that span — so the number lives
    inside it rather than floating in the margin.
    """
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_lane = font(28, bold=True)
    f_ev = font(25, bold=True)
    f_note = font(23)
    f_big = font(42, bold=True)

    x0, x1 = 500, 3080
    shift_x = x0 + int((x1 - x0) * 0.18)

    # --- lane 1: what the monitoring stack sees --------------------------
    y = 130
    d.text((70, y - 42), "MONITORING", font=f_lane, fill=MUTED)
    d.text((70, y + 4), "quarterly", font=f_note, fill=MUTED)
    dashed_h(d, y, x0, x1, LINE, 4)
    for x in (x0, x1):
        d.ellipse([(x - 16, y - 16), (x + 16, y + 16)], fill=ACCENT)
        centred(d, "PSI report", x, y - 52, f_ev, ACCENT)
    centred(d, "no signal in between", (x0 + x1) // 2, y - 52, f_note, MUTED)

    # --- lane 2: what actually happens -----------------------------------
    y = 360
    d.text((70, y - 42), "REALITY", font=f_lane, fill=INK)
    d.text((70, y + 4), "continuous", font=f_note, fill=MUTED)
    d.line([(x0, y), (x1, y)], fill=LINE, width=4)
    d.ellipse([(shift_x - 18, y - 18), (shift_x + 18, y + 18)], fill=BLOCK)
    centred(d, "population shifts", shift_x, y - 52, f_ev, BLOCK)

    # The drop line ties the shift to the exposure window it opens.
    d.line([(shift_x, y + 24), (shift_x, 530)], fill=BLOCK, width=2)

    # --- lane 3: the exposure window, carrying its own number ------------
    y0, y1 = 540, 700
    d.text((70, y0 + 40), "EXPOSURE", font=f_lane, fill=BLOCK)
    d.rounded_rectangle([(shift_x, y0), (x1, y1)], radius=12, fill=(253, 236, 234))
    d.rounded_rectangle([(shift_x, y0), (x1, y1)], radius=12, outline=BLOCK, width=3)
    cx = (shift_x + x1) // 2
    centred(d, "~11 weeks", cx, y0 + 52, f_big, BLOCK)
    centred(
        d,
        "every automated decision here is made by a model nobody knows has drifted",
        cx,
        y0 + 116,
        f_note,
        BLOCK,
    )

    centred(
        d,
        'Practitioner interview: "you need some leading indicators — you cannot wait three months"',
        W // 2,
        H - 55,
        f_note,
        MUTED,
    )

    path = OUT / "problem_timeline.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


def on_path(width_in: float = 11.0, height_in: float = 3.28) -> Path:
    """Why existing tooling does not close the gap: it is not on the path.

    Drawn as a before/after of the *same* request path, because the difference
    is not what these tools measure — it is where they sit. Monitoring observes
    from above and reports afterwards; Custos sits in the path and answers
    before the action happens.
    """
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_h = font(27, bold=True)
    f_box = font(29, bold=True)
    f_small = font(24, bold=True)
    f_note = font(23)
    f_v = font(25, bold=True)

    agent = (70, 620)
    money = (2680, 3230)

    # --- band 1: today ----------------------------------------------------
    d.text((70, 40), "TODAY", font=f_h, fill=MUTED)
    for label, x in (("Evidently", 900), ("WhyLabs", 1500), ("MLflow", 2100)):
        box(d, (x, 95, x + 480, 215), fill=PANEL)
        centred(d, label, x + 240, 155, f_small, MUTED)
        dashed_v(d, x + 240, 225, 320, LINE, 3)

    y = 380
    box(d, (agent[0], y - 60, agent[1], y + 60), fill=PANEL)
    centred(d, "Agent", (agent[0] + agent[1]) // 2, y, f_box)
    box(d, (money[0], y - 60, money[1], y + 60), fill=PANEL)
    centred(d, "money moves", (money[0] + money[1]) // 2, y, f_box)
    arrow(d, (agent[1] + 20, y), (money[0] - 20, y), MUTED, width=5)
    centred(d, "nothing stands between the two", 1650, y + 46, f_note, MUTED)
    centred(d, "observes  ·  reports later  ·  cannot intervene", 1650, 340, f_note, MUTED)

    dashed_h(d, 530, 70, W - 70, LINE, 2)

    # --- band 2: with custos ---------------------------------------------
    d.text((70, 590), "CUSTOS", font=f_h, fill=ACCENT)
    y = 790
    box(d, (agent[0], y - 60, agent[1], y + 60), fill=PANEL)
    centred(d, "Agent", (agent[0] + agent[1]) // 2, y, f_box)

    gx0, gx1 = 1180, 2120
    box(d, (gx0, y - 92, gx1, y + 92), fill=WHITE, outline=ACCENT, width=5)
    centred(d, "CUSTOS", (gx0 + gx1) // 2, y - 42, f_box, ACCENT)
    for label, colour, x in (
        ("ALLOW", ALLOW, 1360),
        ("REVIEW", REVIEW, 1650),
        ("BLOCK", BLOCK, 1940),
    ):
        centred(d, label, x, y + 42, f_v, colour)

    box(d, (money[0], y - 60, money[1], y + 60), fill=PANEL)
    centred(d, "money moves", (money[0] + money[1]) // 2, y, f_box)

    arrow(d, (agent[1] + 20, y), (gx0 - 20, y), ACCENT, width=5)
    arrow(d, (gx1 + 20, y), (money[0] - 20, y), ACCENT, width=5)
    centred(d, "the verdict happens before the action, not after it", 1650, y + 138, f_note, ACCENT)

    path = OUT / "on_path.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


def gap_map(width_in: float = 11.0, height_in: float = 3.2) -> Path:
    """Research gaps mapped to the objectives that answer them."""
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_h = font(28, bold=True)
    f_tag = font(27, bold=True)
    f_txt = font(24)

    rows = [
        (
            "G1",
            "drift never reaches the request path",
            "O1 · O3",
            "fused signal inside a 50 ms budget",
        ),
        ("G2", "one number, no per-feature attribution", "O2", "PSI + KS per feature, ranked"),
        (
            "G3",
            "policy and reliability never combine",
            "O1 · O5",
            "one engine interface, weighted fusion",
        ),
        ("G4", "decision logs are mutable", "O4", "SHA-256 hash chain, verifiable"),
    ]

    d.text((90, 60), "RESEARCH GAP", font=f_h, fill=BLOCK)
    d.text((1900, 60), "OBJECTIVE", font=f_h, fill=ALLOW)

    y = 200
    for tag, gap, obj, how in rows:
        box(d, (90, y, 1560, y + 150), fill=PANEL, outline=BLOCK, width=3)
        centred(d, tag, 190, y + 75, f_tag, BLOCK)
        d.text((290, y + 58), gap, font=f_txt, fill=INK)

        arrow(d, (1590, y + 75), (1860, y + 75), MUTED, width=4)

        box(d, (1900, y, 3230, y + 150), fill=WHITE, outline=ALLOW, width=3)
        centred(d, obj, 2030, y + 75, f_tag, ALLOW)
        d.text((2170, y + 58), how, font=f_txt, fill=INK)
        y += 190

    path = OUT / "gap_map.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


def demo_trajectory(width_in: float = 11.0, height_in: float = 3.4) -> Path:
    """The five demo acts as a trust trajectory.

    The point of the demo in one picture: the model and the code never change,
    and the verdict changes anyway.
    """
    W, H = int(width_in * SCALE), int(height_in * SCALE)
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_act = font(25, bold=True)
    f_v = font(27, bold=True)
    f_note = font(23)
    f_score = font(30, bold=True)

    acts = [
        ("Act 1", "unregistered", 1.00, "REVIEW", REVIEW),
        ("Act 2", "healthy traffic", 0.99, "ALLOW", ALLOW),
        ("Act 3", "population shifts", None, "drift 0.02 -> 0.83", BLOCK),
        ("Act 4", "same input, same code", 0.48, "REVIEW", REVIEW),
        ("Act 5", "policy veto", 0.00, "BLOCK", BLOCK),
    ]

    x0, step = 260, 700
    base, top = 760, 220  # trust 0.0 and 1.0 on the y axis

    def y_of(score):
        return base - score * (base - top)

    # axis
    d.line([(150, base), (W - 90, base)], fill=LINE, width=3)
    d.line([(150, top - 40), (150, base)], fill=LINE, width=3)
    for score in (0.0, 0.6, 1.0):
        y = y_of(score)
        dashed_h(d, y, 160, W - 90, LINE, 2)
        centred(d, f"{score:.1f}", 100, y, f_note, MUTED)
    centred(d, "review", 100, y_of(0.6) - 34, f_note, REVIEW)
    centred(d, "trust", 100, top - 70, f_note, MUTED)

    pts = [(x0 + i * step, y_of(s)) for i, (_, _, s, _, _) in enumerate(acts) if s is not None]
    # Pairwise walk: the two sequences differ in length by one by design.
    for a, b in zip(pts, pts[1:], strict=False):
        d.line([a, b], fill=MUTED, width=4)

    for i, (act, sub, score, verdict, colour) in enumerate(acts):
        x = x0 + i * step
        centred(d, act, x, base + 62, f_act, INK)
        centred(d, sub, x, base + 106, f_note, MUTED)

        if score is None:
            # Act 3 is an event, not a verdict. It still gets a chip so the
            # bottom row keeps its rhythm — filled rather than outlined, so it
            # reads as "something happened here", not "this was the answer".
            centred(d, verdict, x, y_of(0.52), f_v, colour)
            centred(d, "no code or config change", x, y_of(0.52) + 44, f_note, MUTED)
            d.rounded_rectangle(
                [(x - 150, base + 150), (x + 150, base + 226)], radius=14, fill=colour
            )
            centred(d, "DRIFT DETECTED", x, base + 188, f_note, WHITE)
            continue

        y = y_of(score)
        d.ellipse([(x - 15, y - 15), (x + 15, y + 15)], fill=colour)
        centred(d, f"{score:.2f}", x, y - 52, f_score, colour)
        box(d, (x - 130, base + 150, x + 130, base + 226), fill=WHITE, outline=colour, width=4)
        centred(d, verdict, x, base + 188, f_v, colour)

    path = OUT / "demo_trajectory.png"
    img.save(path, dpi=(SCALE, SCALE))
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    figures = (
        problem_timeline(),
        on_path(),
        gap_map(),
        architecture(),
        request_flow(),
        drift_pipeline(),
        decision_flow(),
        demo_trajectory(),
        drift_chart(),
        calibration_curve(),
        load_profile(),
    )
    for path in figures:
        print(f"wrote {path.relative_to(Path.cwd()) if path.is_absolute() else path}")


if __name__ == "__main__":
    main()
