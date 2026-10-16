"""Build the Phase-2 Review-1 deck from the department's .pptx template.

    python docs/presentations/build_deck.py

Regenerates `Custos_Phase2_Review1.pptx` end to end: unpack the template,
duplicate its content slide as many times as the narrative needs, put the slides
in order, fill every title and body, fill the literature-survey table, and place
every generated table and figure.

Written as a script rather than done by hand because the deck has to be rebuilt
for each review. Editing 22 slides by hand once is tedious; doing it again in a
month, consistently, is where mistakes get made.

The template is never modified — it is unpacked to a scratch directory and the
output is written beside this file.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import content

HERE = Path(__file__).parent
TEMPLATE = HERE / "template" / "Project Work phase-2 PPT format.pptx"
OUTPUT = HERE / "Custos_Phase2_Review1.pptx"
FIGURES = HERE / "figures"
WORK = HERE / ".build"

# --- run-level formatting, copied from the template's own body runs ---------

FONT = (
    '<a:latin typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="0"/>'
    '<a:ea typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="0"/>'
    '<a:cs typeface="Calibri" panose="020F0502020204030204" pitchFamily="34" charset="0"/>'
)
BULLET_FONT = (
    '<a:buFont typeface="Arial" panose="020B0604020202020204" pitchFamily="34" charset="0"/>'
)

TITLE_PH = 'type="ctrTitle"'
BODY_PH = 'type="subTitle"'

REVIEW_DATE = "12 September 2026"


def run(text: str, size: int, bold: bool = False, italic: bool = False) -> str:
    return (
        f'<a:r><a:rPr lang="en-US" sz="{size}" b="{int(bold)}" i="{int(italic)}" dirty="0">'
        f"{FONT}</a:rPr><a:t>{escape(text)}</a:t></a:r>"
    )


def para(
    runs: str, level: int = 0, space_before: int = 400, bullet: bool = True, align: str = "l"
) -> str:
    if bullet and level == 0:
        marker, mar, ind = f'{BULLET_FONT}<a:buChar char="•"/>', 285750, -285750
    elif bullet:
        marker, mar, ind = f'{BULLET_FONT}<a:buChar char="–"/>', 685800, -228600
    else:
        marker, mar, ind = "<a:buNone/>", 0, 0
    spc = f'<a:spcBef><a:spcPts val="{space_before}"/></a:spcBef>'
    return (
        f'<a:p><a:pPr marL="{mar}" indent="{ind}" algn="{align}">{spc}{marker}</a:pPr>{runs}</a:p>'
    )


def bullet(
    text: str, size: int = 1600, bold_prefix: str | None = None, space_before: int = 400
) -> str:
    runs = run(bold_prefix, size, bold=True) if bold_prefix else ""
    return para(runs + run(text, size), space_before=space_before)


def plain(
    text: str,
    size: int = 1600,
    bold: bool = False,
    italic: bool = False,
    align: str = "l",
    space_before: int = 400,
) -> str:
    return para(
        run(text, size, bold=bold, italic=italic),
        space_before=space_before,
        bullet=False,
        align=align,
    )


def heading(text: str, size: int = 3200) -> str:
    return plain(text, size=size, bold=True, align="l", space_before=0)


# --- XML surgery -----------------------------------------------------------


def set_body(xml: str, ph_pattern: str, paragraphs: list[str]) -> str:
    """Replace the txBody of the one shape carrying ``ph_pattern``."""
    body = (
        "<p:txBody><a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/>"
        + "".join(paragraphs)
        + "</p:txBody>"
    )
    out: list[str] = []
    last = count = 0
    for m in re.finditer(r"<p:sp>(?:(?!</p:sp>).)*?</p:sp>", xml, re.S):
        if ph_pattern in m.group():
            out.append(xml[last : m.start()])
            out.append(re.sub(r"<p:txBody>.*?</p:txBody>", body, m.group(), flags=re.S))
            last, count = m.end(), count + 1
    out.append(xml[last:])
    if count != 1:
        raise AssertionError(f"expected exactly one {ph_pattern} shape, found {count}")
    return "".join(out)


def write_slide(slide_file: str, title: list[str], body: list[str]) -> None:
    path = WORK / "ppt" / "slides" / slide_file
    xml = path.read_text()
    xml = set_body(xml, TITLE_PH, title)
    xml = set_body(xml, BODY_PH, body)
    xml = xml.replace("3 September 2026", REVIEW_DATE)
    path.write_text(xml)


def duplicate_slides(count: int, source: str = "slide3.xml") -> None:
    """Clone the template's plain content slide ``count`` times."""
    script = (
        Path.home() / "Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin"
    )
    add_slide = next(script.rglob("skills/pptx/scripts/add_slide.py"), None)
    if add_slide is None:
        raise SystemExit("add_slide.py not found; cannot duplicate slides")
    for _ in range(count):
        subprocess.run(
            [sys.executable, str(add_slide), str(WORK), source],
            check=True,
            capture_output=True,
        )


def reorder(order: list[str]) -> None:
    """Rewrite <p:sldIdLst> so the slides appear in narrative order."""
    rels = (WORK / "ppt/_rels/presentation.xml.rels").read_text()
    rid = {
        m.group(2): m.group(1)
        for m in re.finditer(
            r'<Relationship Id="([^"]+)"[^>]*Target="slides/(slide\d+\.xml)"', rels
        )
    }
    missing = [f for f in order if f not in rid]
    if missing:
        raise AssertionError(f"slides missing from package: {missing}")

    listing = "".join(f'<p:sldId id="{256 + i}" r:id="{rid[f]}"/>' for i, f in enumerate(order))
    pres_path = WORK / "ppt/presentation.xml"
    pres = re.sub(
        r"<p:sldIdLst>.*?</p:sldIdLst>",
        f"<p:sldIdLst>{listing}</p:sldIdLst>",
        pres_path.read_text(),
        flags=re.S,
    )
    pres_path.write_text(pres)



# --- deck content ----------------------------------------------------------
#
# Twenty-two slides. Text on a slide is there to frame the visual under it, never
# to be read aloud — anything that needs a paragraph belongs in the report, not
# on a projector.


def fill_all() -> None:
    # ---------------------------------------------------------------- 1 title
    names = []
    for i, (name, usn) in enumerate(content.TEAM):
        names.append(
            plain(f"{name}\t\t{usn}", 1600, bold=True, align="ctr", space_before=200 if i == 0 else 120)
        )

    write_slide(
        "slide1.xml",
        [
            plain("BMS College of Engineering", 2800, bold=True, align="ctr", space_before=0),
            plain("(Autonomous College under VTU)", 1400, align="ctr", space_before=100),
            plain(
                "Department of Artificial Intelligence and Data Science",
                1600, bold=True, align="ctr", space_before=250,
            ),
            plain(
                "Project Work Phase-II (23AI7PWPP1) — Review-1",
                1400, align="ctr", space_before=350,
            ),
            plain("CUSTOS", 3200, bold=True, align="ctr", space_before=350),
            plain(
                "Runtime Drift Enforcement for Production ML Models",
                1800, align="ctr", space_before=120,
            ),
        ],
        [
            plain("Presented by", 1300, italic=True, align="ctr", space_before=0),
            *names,
            plain("Under the guidance of", 1300, italic=True, align="ctr", space_before=400),
            plain(content.GUIDE, 1700, bold=True, align="ctr", space_before=150),
            plain("Dept. of AI & DS, BMSCE", 1400, align="ctr", space_before=60),
        ],
    )

    # ------------------------------------------------------------- 2 contents
    write_slide(
        "slide2.xml",
        [heading("Contents")],
        [
            bullet("The problem — and why existing tooling does not close it", 1800),
            bullet("Literature survey and research gap", 1800),
            bullet("Objectives, scope and requirements", 1800),
            bullet("System design — architecture, request flow, drift pipeline, decision logic", 1800),
            bullet("Implementation status", 1800),
            bullet("Results — live demonstration and drift attribution", 1800),
            bullet("Data and validation — how the detector is calibrated, and against what", 1800),
            bullet("Engineering rigour — load testing, the defects it found, and the fixes", 1800),
            bullet("Team contributions and conclusion", 1800),
        ],
    )

    # -------------------------------------------------------------- 3 problem
    write_slide(
        "slide3.xml",
        [heading("The Problem")],
        [
            plain(
                "A model is validated once, deployed, and then trusted indefinitely. Drift is "
                "checked on a quarterly report — but decisions are made every second.",
                1500, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------- 4 why tooling falls short
    write_slide(
        "slide4.xml",
        [heading("Why Existing Tooling Does Not Close It")],
        [
            plain(
                "The tools exist. They sit beside the request path and report afterwards. None of "
                "them can stop the decision that is about to be made.",
                1500, space_before=0,
            ),
        ],
    )

    # ---------------------------------------------------- 5 literature survey
    write_slide(
        "slide5.xml",
        [heading("Literature Survey")],
        [
            plain(
                "Six works across three areas: ML systems infrastructure, distribution-shift "
                "detection, and tamper-evident logging.",
                1400, space_before=0,
            )
        ],
    )

    # -------------------------------------------------- 6 research gap mapping
    write_slide(
        "slide10.xml",
        [heading("Research Gap and Objectives")],
        [
            plain(
                "Every gap the survey identified maps to an objective, and every objective is "
                "implemented and demonstrated.",
                1500, space_before=0,
            ),
        ],
    )

    # ------------------------------------------- 7 objectives, scope, SDG
    write_slide(
        "slide11.xml",
        [heading("Scope and SDG Alignment")],
        [
            plain("In scope", 1750, bold=True, space_before=0),
            bullet(
                "Drift detection with per-feature attribution, policy evaluation, signal fusion, "
                "runtime enforcement, tamper-evident audit, multi-tenant configuration.",
                1500,
            ),
            plain("Out of scope", 1750, bold=True, space_before=400),
            bullet(
                "Custos does not train, serve or host models. It does not explain individual "
                "predictions, and it does not retrain or roll back. It decides and records — "
                "humans act.",
                1500,
            ),
            plain("SDG alignment", 1750, bold=True, space_before=400),
            bullet("Industry, Innovation and Infrastructure — auditable infrastructure for automated decisions.", 1500, bold_prefix="SDG 9  "),
            bullet("Reduced Inequalities — blocking a drifted model limits systematically unfair credit decisions.", 1500, bold_prefix="SDG 10  "),
            bullet("Peace, Justice and Strong Institutions — verifiable records support regulatory audit.", 1500, bold_prefix="SDG 16  "),
        ],
    )

    # --------------------------------------------------------- 8 requirements
    write_slide(
        "slide6.xml",
        [heading("Requirements")],
        [
            plain(
                "Ten functional requirements and six non-functional ones. The latency and "
                "fail-open constraints drove most of the architecture.",
                1400, space_before=0,
            ),
        ],
    )

    # --------------------------------------------------------- 9 architecture
    write_slide(
        "slide7.xml",
        [heading("System Architecture")],
        [
            plain(
                "Two planes. The data plane does the minimum possible work per request; "
                "everything expensive lives on the control plane or in the offline worker.",
                1400, space_before=0,
            ),
        ],
    )

    # -------------------------------------------------------- 10 request flow
    write_slide(
        "slide12.xml",
        [heading("Request Flow")],
        [
            plain(
                "One /v1/evaluate call. Steps 2, 3 and 5 are cached reads; step 7 is pure "
                "computation; only 8 and 10 touch the database — and 10 runs after the caller "
                "already has its answer.",
                1350, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------------- 11 drift pipeline
    write_slide(
        "slide13.xml",
        [heading("Drift Pipeline")],
        [
            plain(
                "Where the statistics run, and where they do not. This split is what makes a "
                "50 ms budget achievable while still computing PSI and KS over full windows.",
                1350, space_before=0,
            ),
        ],
    )

    # ----------------------------------------------------- 12 decision cascade
    write_slide(
        "slide14.xml",
        [heading("Decision Logic")],
        [
            plain(
                "Signals fuse as a weighted mean over non-degraded engines; a veto clamps the "
                "score to zero. The cascade below is then evaluated in order — the order is the "
                "specification.",
                1350, space_before=0,
            ),
        ],
    )

    # -------------------------------------------------- 13 implementation status
    write_slide(
        "slide8.xml",
        [heading("Implementation Status")],
        [
            plain(
                "Nine of eleven components are complete and exercised end to end. The remaining "
                "two are deliberate, not unfinished.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------------ 14 live demo
    write_slide(
        "slide15.xml",
        [heading("Results — Live Demonstration")],
        [
            plain(
                "A lending agent auto-approves loans behind Custos. One command, no external "
                "infrastructure. The model and the code never change — only the incoming "
                "population does.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------- 15 drift attribution
    write_slide(
        "slide16.xml",
        [heading("Results — Drift Attribution")],
        [
            plain(
                "Severity says the model moved; attribution says which input moved — the "
                "difference between a population shift and a broken upstream feed.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------ 16 data and validation
    write_slide(
        "slide20.xml",
        [heading("Data and Validation")],
        [
            plain(
                "Custos contains no trained model, no fitted parameters, no weights. It is a "
                "measuring instrument — so it is validated the way instruments are, by "
                "calibration against known inputs, not by accuracy on held-out data.",
                1400, space_before=0,
            ),
            plain(
                "A thermometer is not validated by pointing it at random objects. It goes into "
                "melting ice to read 0 °C and boiling water to read 100 °C. The reference points "
                "have to be known, or the reading cannot be checked against anything.",
                1300, space_before=260,
            ),
        ],
    )

    # ---------------------------------------------- 17 the calibration result
    write_slide(
        "slide21.xml",
        [heading("Calibration — the Instrument in Ice and Steam")],
        [
            plain(
                "Shift a feature's mean by a chosen number of standard deviations and check what "
                "PSI reports back. Because the input was chosen, the correct output is known — "
                "which is precisely what real data cannot offer.",
                1400, space_before=0,
            ),
        ],
    )

    # --------------------------------------------- 18 what calibration proves
    write_slide(
        "slide22.xml",
        [heading("What the Controlled Data Proves")],
        [
            plain(
                "Five properties, 43 detector tests. The right-hand column is the answer to "
                "“why not just use a real dataset?” — none of these could be checked on one.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------- 19 validating the claim
    write_slide(
        "slide17.xml",
        [heading("Validating the Latency Claim")],
        [
            plain(
                "NFR1 asserts a 50 ms p99. An assertion in a design document is not evidence, "
                "so we built the instrument that could falsify it — and it did.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------- 17 what load testing exposed
    write_slide(
        "slide18.xml",
        [heading("What Load Testing Exposed")],
        [
            plain(
                "Three defects, none of them reachable by a test that sends one request at a "
                "time. This is the difference between a suite that passes and a system that works.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------- 18 the audit chain defect
    write_slide(
        "slide19.xml",
        [heading("Case Study — The Audit Log That Lied")],
        [
            plain(
                "Our strongest claim is tamper-evident evidence for every decision. Under "
                "concurrency it was dropping entries and reporting itself intact.",
                1400, space_before=0,
            ),
            plain("Symptom", 1500, bold=True, space_before=280),
            bullet("At 24 concurrent writers, 2 of 96 appends were lost — and GET /audit/verify still returned “all 94 entries verified”. A hash chain detects a modified entry, never a missing one.", 1300),
            plain("Diagnosis before cure", 1500, bold=True, space_before=200),
            bullet("Measured where it was actually reachable: 0 lost at 1 uvicorn worker, 2 lost at 4. The event loop already serialised single-worker writes, so the obvious per-tenant in-process lock would have protected the only configuration that was not broken.", 1300),
            plain("Fix", 1500, bold=True, space_before=200),
            bullet("Postgres: pg_advisory_xact_lock per tenant, taken before the chain head is read. Every backend: jittered backoff, because five instant retries kept the racers in lockstep. Result: 0 lost from 2 to 48 writers — and 2× the throughput, since the retry storm was itself the load.", 1300),
        ],
    )

    # ---------------------------------------- 19 contributions and conclusion
    write_slide(
        "slide9.xml",
        [heading("Contributions and Conclusion")],
        [
            plain(
                "274 tests passing · 50 ms p99 budget verified under load to 100 req/s per "
                "instance · two concurrency defects found by our own harness and fixed · "
                "audit chain demonstrated under an actual tampering attempt.",
                1400, bold=True, space_before=0,
            ),
            plain("Next, for Review-2", 1600, bold=True, space_before=320),
            bullet("Admission control: shed load at the door rather than let a spike silently convert auto-approvals into review backlog.", 1350),
            bullet("Validate against real drift using the Lending Club dataset, replacing the controlled synthetic scenarios.", 1350),
            bullet("Model and data versioning, plus a retraining trigger — the components practitioners named as prerequisites.", 1350),
            bullet("Move the audit write off the hot path, and re-measure against Postgres rather than SQLite.", 1350),
        ],
    )


# --- tables and figures (python-pptx, after repacking) ----------------------
#
# Keyed by slide *file*, not by position: position shifts whenever a slide is
# inserted, and a stale index silently drops content onto the wrong slide.

TABLE_SLIDES = {
    "slide6.xml": (content.REQUIREMENTS, 2.70),
    "slide8.xml": (content.MODULE_STATUS, 2.70),
    "slide20.xml": (content.VALIDATION_TRACKS, 4.30),
    "slide22.xml": (content.CALIBRATION_EVIDENCE, 2.70),
    "slide18.xml": (content.LOAD_FINDINGS, 2.70),
    "slide9.xml": (content.CONTRIBUTIONS, 4.75),
}

FIGURE_SLIDES = {
    "slide3.xml": ("problem_timeline.png", 2.85, 11.0),
    "slide4.xml": ("on_path.png", 2.75, 10.6),
    "slide10.xml": ("gap_map.png", 2.85, 11.0),
    "slide7.xml": ("architecture.png", 2.95, 11.0),
    "slide12.xml": ("request_flow.png", 2.55, 10.4),
    "slide13.xml": ("drift_pipeline.png", 2.95, 11.0),
    "slide14.xml": ("decision_flow.png", 3.00, 11.0),
    "slide15.xml": ("demo_trajectory.png", 2.80, 11.0),
    "slide16.xml": ("drift_attribution.png", 2.90, 11.0),
    "slide21.xml": ("calibration_curve.png", 2.75, 11.0),
    "slide17.xml": ("load_profile.png", 2.80, 11.0),
}

SLIDE_WIDTH_IN = 13.333
TABLE_LEFT_IN = 1.05
TABLE_WIDTH_IN = 11.2
HEADER_FILL = "1F5CA8"
ZEBRA_FILL = "F4F6F9"


def _style_cell(cell, text, size, bold=False, colour=None, fill=None):
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    cell.margin_left = cell.margin_right = Pt(5)
    cell.margin_top = cell.margin_bottom = Pt(3)
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor.from_string(fill)
    else:
        cell.fill.background()

    frame = cell.text_frame
    frame.word_wrap = True
    para = frame.paragraphs[0]
    for existing in list(para.runs):
        existing._r.getparent().remove(existing._r)
    run_ = para.add_run()
    run_.text = text
    run_.font.size = Pt(size)
    run_.font.bold = bold
    run_.font.name = "Calibri"
    if colour is not None:
        run_.font.color.rgb = RGBColor.from_string(colour)


def add_table(slide, spec, top_in: float, font_pt: float = 11.0) -> None:
    """Place a table below the slide's framing line.

    Row heights are set to the minimum PowerPoint honours; it grows any row
    whose text needs more, so setting them small keeps the table as short as
    its content allows rather than padding every row to a fixed height.
    """
    from pptx.util import Emu, Inches, Pt

    headers, rows, fractions = spec
    if abs(sum(fractions) - 1.0) > 1e-6:
        raise AssertionError(f"column fractions must sum to 1.0, got {sum(fractions)}")
    if any(len(r) != len(headers) for r in rows):
        raise AssertionError("every row must have as many cells as there are headers")

    shape = slide.shapes.add_table(
        len(rows) + 1,
        len(headers),
        Inches(TABLE_LEFT_IN),
        Inches(top_in),
        Inches(TABLE_WIDTH_IN),
        Inches(0.3 * (len(rows) + 1)),
    )
    table = shape.table
    table.first_row = True
    table.horz_banding = False  # applied explicitly below

    for col, frac in zip(table.columns, fractions, strict=True):
        col.width = Emu(int(Inches(TABLE_WIDTH_IN) * frac))

    for c, text in enumerate(headers):
        _style_cell(table.cell(0, c), text, font_pt, bold=True, colour="FFFFFF", fill=HEADER_FILL)

    for r, row in enumerate(rows, start=1):
        fill = ZEBRA_FILL if r % 2 == 0 else None
        for c, text in enumerate(row):
            _style_cell(table.cell(r, c), text, font_pt, fill=fill)

    for row in table.rows:
        row.height = Pt(2)


def finish(path: Path) -> None:
    """Fill the template's literature table, then add every generated table and figure."""
    from pptx import Presentation
    from pptx.util import Emu, Inches, Pt

    prs = Presentation(str(path))

    # -- the template's own table, on the literature survey slide --
    slide = prs.slides[ORDER.index("slide5.xml")]
    shape = next(sh for sh in slide.shapes if sh.has_table)
    shape.left, shape.top, shape.width = Inches(1.05), Inches(2.45), Inches(11.2)
    for col, frac in zip(shape.table.columns, content.LITERATURE_COLUMNS, strict=True):
        col.width = Emu(int(Inches(11.2) * frac))

    # The template ships a fixed number of body rows. Grow it by deep-copying
    # the last row element, which carries the template's own cell formatting —
    # python-pptx has no public API for adding a row.
    import copy

    tbl = shape.table._tbl
    while len(tbl.tr_lst) - 1 < len(content.LITERATURE):
        tbl.append(copy.deepcopy(tbl.tr_lst[-1]))

    for r, values in enumerate(content.LITERATURE, start=1):
        for c, text in enumerate(values):
            cell = shape.table.cell(r, c)
            frame = cell.text_frame
            frame.word_wrap = True
            para = frame.paragraphs[0]
            for existing in list(para.runs):
                existing._r.getparent().remove(existing._r)
            # A newline in the source splits title from authors; the second
            # line is set smaller so the citation reads as a subtitle.
            for i, line in enumerate(text.split("\n")):
                target = para if i == 0 else frame.add_paragraph()
                cell_run = target.add_run()
                cell_run.text = line
                cell_run.font.size = Pt(8.5 if i else 9.0)
                cell_run.font.name = "Calibri"
                cell_run.font.italic = bool(i)
    for c in range(6):
        for para in shape.table.cell(0, c).text_frame.paragraphs:
            for header_run in para.runs:
                header_run.font.size = Pt(10.0)
                header_run.font.bold = True

    # -- generated tables --
    for slide_file, (spec, top_in) in TABLE_SLIDES.items():
        rows = len(spec[1])
        add_table(
            prs.slides[ORDER.index(slide_file)],
            spec,
            top_in,
            font_pt=9.5 if rows >= 10 else 11.0,
        )

    # -- figures, centred on their own width --
    for slide_file, (name, top_in, width_in) in FIGURE_SLIDES.items():
        left_in = (SLIDE_WIDTH_IN - width_in) / 2
        prs.slides[ORDER.index(slide_file)].shapes.add_picture(
            str(FIGURES / name), Inches(left_in), Inches(top_in), width=Inches(width_in)
        )

    prs.save(str(path))


# --- orchestration ---------------------------------------------------------

ORDER = [
    "slide1.xml",   #  1 title
    "slide2.xml",   #  2 contents
    "slide3.xml",   #  3 the problem                     [figure]
    "slide4.xml",   #  4 why existing tooling fails      [figure]
    "slide5.xml",   #  5 literature survey               [table]
    "slide10.xml",  #  6 research gap -> objectives      [figure]
    "slide11.xml",  #  7 scope and SDGs
    "slide6.xml",   #  8 requirements                    [table]
    "slide7.xml",   #  9 system architecture             [figure]
    "slide12.xml",  # 10 request flow                    [figure]
    "slide13.xml",  # 11 drift pipeline                  [figure]
    "slide14.xml",  # 12 decision logic                  [figure]
    "slide8.xml",   # 13 implementation status           [table]
    "slide15.xml",  # 14 results — live demonstration    [figure]
    "slide16.xml",  # 15 results — drift attribution     [figure]
    # Validation: what the data is for, then the calibration itself, then what
    # it proves. This block answers "where is your dataset?" before it is asked.
    "slide20.xml",  # 16 data and validation             [table]
    "slide21.xml",  # 17 calibration curve               [figure]
    "slide22.xml",  # 18 what controlled data proves     [table]
    # Engineering rigour: the claim, the measurement, the defect, the fix.
    "slide17.xml",  # 19 validating the latency claim    [figure]
    "slide18.xml",  # 20 what load testing exposed       [table]
    "slide19.xml",  # 21 case study — the audit log      [text]
    "slide9.xml",   # 22 contributions and conclusion    [table]
]

# Template ships 9 slides; the rest are clones of its plain content slide.
DUPLICATES = len(ORDER) - 9


def main() -> None:
    if not TEMPLATE.exists():
        raise SystemExit(f"template not found: {TEMPLATE}")
    missing = [n for n, _, _ in FIGURE_SLIDES.values() if not (FIGURES / n).exists()]
    if missing:
        raise SystemExit(f"figures missing {missing} — run make_figures.py first")

    unknown = (set(TABLE_SLIDES) | set(FIGURE_SLIDES)) - set(ORDER)
    if unknown:
        raise AssertionError(f"table/figure targets not in ORDER: {sorted(unknown)}")

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    with zipfile.ZipFile(TEMPLATE) as z:
        z.extractall(WORK)

    # Structural work first: duplicating a slide copies it verbatim, so any
    # content written before this point would be cloned along with it.
    duplicate_slides(DUPLICATES)
    reorder(ORDER)
    fill_all()

    OUTPUT.unlink(missing_ok=True)
    subprocess.run(["zip", "-Xrq", str(OUTPUT), "."], cwd=WORK, check=True, capture_output=True)
    finish(OUTPUT)
    shutil.rmtree(WORK, ignore_errors=True)

    print(
        f"built {OUTPUT.name} — {len(ORDER)} slides, "
        f"{len(TABLE_SLIDES) + 1} tables, {len(FIGURE_SLIDES)} figures"
    )


if __name__ == "__main__":
    main()
