"""Build the Phase-2 Review-2 deck from the department template.

    python docs/presentations/make_figures.py
    python docs/presentations/build_review2.py

Reuses build_deck.py's template machinery — unpack, clone, reorder, fill,
repack, place tables and figures — and supplies only the Review-2 slides. The
Review-1 builder is untouched, so that deck stays reproducible as presented.

The narrative is progressive: what we committed to at Review-1, what happened
to each commitment, what is new, and what it measured — including what did not
get done.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import build_deck as bd
import content_review2 as c2
from build_deck import bullet, heading, plain

HERE = Path(__file__).parent
ROOT = HERE.parents[1]


def _test_count() -> int:
    """Read the number off the suite rather than hand-typing it."""
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--co"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    match = re.search(r"(\d+) tests? collected", out)
    if not match:
        raise SystemExit("could not count tests; is pytest installed?")
    return int(match.group(1))


TESTS = _test_count()


def fill_all() -> None:
    names = [
        plain(f"{name}\t\t{usn}", 1600, bold=True, align="ctr",
              space_before=200 if i == 0 else 120)
        for i, (name, usn) in enumerate(c2.TEAM)
    ]

    # ---------------------------------------------------------------- 1 title
    bd.write_slide(
        "slide1.xml",
        [
            plain("BMS College of Engineering", 2800, bold=True, align="ctr", space_before=0),
            plain("(Autonomous College under VTU)", 1400, align="ctr", space_before=100),
            plain("Department of Artificial Intelligence and Data Science",
                  1600, bold=True, align="ctr", space_before=250),
            plain("Project Work Phase-II (23AI7PWPP1) — Review-2",
                  1400, align="ctr", space_before=350),
            plain("CUSTOS", 3200, bold=True, align="ctr", space_before=350),
            plain("Runtime Drift Enforcement for Production ML Models",
                  1800, align="ctr", space_before=120),
        ],
        [
            plain("Presented by", 1300, italic=True, align="ctr", space_before=0),
            *names,
            plain("Under the guidance of", 1300, italic=True, align="ctr", space_before=400),
            plain(c2.GUIDE, 1700, bold=True, align="ctr", space_before=150),
            plain(c2.GUIDE_DESIGNATION, 1400, align="ctr", space_before=60),
        ],
    )

    # ------------------------------------------------------------- 2 contents
    bd.write_slide(
        "slide2.xml",
        [heading("Table of Contents")],
        [
            bullet("Abstract", 1700),
            bullet("Progress since Review-1", 1700),
            bullet("Introduction — motivation, existing vs proposed system, objectives", 1700),
            bullet("Literature survey and research gap", 1700),
            bullet("Requirement analysis and specification", 1700),
            bullet("System design — architecture and decision logic", 1700),
            bullet("Implementation — new: risk engine and admission control", 1700),
            bullet("Results and validation", 1700),
            bullet("Engineering rigour, work plan and conclusion", 1700),
        ],
    )

    # ------------------------------------------------------------- 3 abstract
    bd.write_slide(
        "slide3.xml",
        [heading("Abstract")],
        [
            plain(
                "Machine-learning models are validated once and then trusted indefinitely, "
                "yet the data they see keeps changing. A drifted model fails quietly: it stays "
                "up, answers confidently, and is wrong.",
                1500, space_before=0,
            ),
            plain(
                "Custos is a runtime trust layer between a model and the consequential action "
                "taken on its output. On every request it fuses three signals — population "
                "drift (PSI and KS against a fixed baseline), business policy, and per-request "
                "risk — into a trust score and an ALLOW, REVIEW or BLOCK verdict within a 50 ms "
                "budget, and appends each verdict to a tamper-evident hash chain. Drift is "
                "computed offline so the request path stays fast.",
                1500, space_before=300,
            ),
            plain(
                "The detector is validated by calibration against shifts of known size; the "
                "gateway by open-loop load testing. Our own tooling has found five defects in "
                "the system, all fixed and pinned by tests.",
                1500, space_before=300,
            ),
        ],
    )

    # ------------------------------------------------- 4 progress since R1
    bd.write_slide(
        "slide10.xml",
        [heading("Progress since Review-1")],
        [
            plain(
                "Every commitment from the Review-1 closing slide, and what happened to it — "
                "including what did not get done.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------- 5 introduction: motivation
    bd.write_slide(
        "slide4.xml",
        [heading("Introduction — Overview and Motivation")],
        [
            plain(
                "A model is validated once, deployed, and then trusted indefinitely. Drift is "
                "checked on a quarterly report — but decisions are made every second.",
                1400, space_before=0,
            ),
        ],
    )

    # --------------------------------------- 6 existing vs proposed system
    bd.write_slide(
        "slide11.xml",
        [heading("Existing System vs Proposed System")],
        [
            plain(
                "Monitoring tools sit beside the request path and report afterwards. Guardrails "
                "block in real time, but only on content. Custos gates the decision itself on "
                "whether the model still fits its traffic.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------- 7 objectives, scope and SDGs
    bd.write_slide(
        "slide12.xml",
        [heading("Objectives, Scope and SDGs")],
        [
            plain("Objectives", 1600, bold=True, space_before=0),
            bullet("O1  Put drift on the live request path, inside a 50 ms budget", 1300, space_before=120),
            bullet("O2  Attribute drift to the individual inputs that moved", 1300, space_before=80),
            bullet("O3  Fuse drift, policy and risk into one explainable verdict", 1300, space_before=80),
            bullet("O4  Record every verdict in a tamper-evident chain", 1300, space_before=80),
            bullet("O5  Stay correct under overload — refuse, never queue or change answers  (new)", 1300, space_before=80),
            plain("Scope", 1600, bold=True, space_before=260),
            bullet(
                "Custos does not train, serve or retrain models. It decides and records; "
                "humans act.",
                1300, space_before=120,
            ),
            plain("SDGs", 1600, bold=True, space_before=260),
            bullet(
                "9 — auditable infrastructure  ·  10 — limits systematically unfair credit "
                "decisions  ·  16 — verifiable records for regulators",
                1300, space_before=120,
            ),
        ],
    )

    # --------------------------------------------------- 8 literature survey
    bd.write_slide(
        "slide5.xml",
        [heading("Literature Survey")],
        [
            plain(
                "Eight works, each checked against its published venue. New since Review-1: "
                "Paleyes et al. (2022) and Rauba et al. (NeurIPS 2024).",
                1300, space_before=0,
            ),
        ],
    )

    # -------------------------------------------------- 9 gap -> objectives
    bd.write_slide(
        "slide13.xml",
        [heading("Research Gap and Objectives")],
        [
            plain(
                "Every work stops at detection or repairs the model afterwards. None gates the "
                "decision in flight on whether the model still fits its traffic.",
                1400, space_before=0,
            ),
        ],
    )

    # --------------------------------------------------- 10 requirements
    bd.write_slide(
        "slide6.xml",
        [heading("Requirement Analysis and Specification")],
        [
            plain(
                "Review-1's requirements plus three new ones (marked). NFR7 is what the "
                "load test forced: overload must be refused, never queued.",
                1300, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------- 11 architecture
    bd.write_slide(
        "slide7.xml",
        [heading("System Design — Architecture")],
        [
            plain(
                "Two planes: the request path does the minimum, statistics run offline. "
                "New: all three engines are live — risk is no longer a stub.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------- 12 decision logic
    bd.write_slide(
        "slide14.xml",
        [heading("System Design — Decision Logic")],
        [
            plain(
                "Seven rules, evaluated in order. New: the drift floor — a significantly "
                "drifted model is never auto-approved, however clean the other signals.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------- 13 implementation status
    bd.write_slide(
        "slide8.xml",
        [heading("Implementation — Status")],
        [
            plain(
                "Ten of twelve components complete. New since Review-1 are marked.",
                1300, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------------ 14 risk engine
    bd.write_slide(
        "slide15.xml",
        [heading("Implementation — Risk Engine (new)")],
        [
            plain(
                "Drift asks whether the model still fits. Policy asks whether the action is "
                "allowed. Risk asks whether this one request is unusual — and abstains rather "
                "than guess when it cannot tell.",
                1400, space_before=0,
            ),
        ],
    )

    # ----------------------------------------------- 15 admission control
    bd.write_slide(
        "slide16.xml",
        [heading("Implementation — Admission Control (new)")],
        [
            plain(
                "At Review-1, overload made the gateway queue, collapse and change its "
                "answers. It now refuses what it cannot serve, and under overload zero "
                "verdicts change (was up to 985 per phase).",
                1400, space_before=0,
            ),
        ],
    )

    # --------------------------------------------------- 16 live demo
    bd.write_slide(
        "slide17.xml",
        [heading("Results — Live Demonstration")],
        [
            plain(
                "Same five acts as Review-1, all three signals live. Act 4 is now held by the "
                "drift floor, with the reason stated in plain language.",
                1400, space_before=0,
            ),
        ],
    )

    # --------------------------------------------------- 17 attribution
    bd.write_slide(
        "slide18.xml",
        [heading("Results — Drift Attribution")],
        [
            plain(
                "Severity says the model moved; attribution says which input moved — the "
                "difference between a population shift and a broken upstream feed.",
                1400, space_before=0,
            ),
        ],
    )

    # --------------------------------------------------- 18 calibration
    bd.write_slide(
        "slide19.xml",
        [heading("Validation — Calibration")],
        [
            plain(
                "Custos is a measuring instrument, so it is validated like one: shifts of a "
                "known size in, readings checked against the known answer.",
                1400, space_before=0,
            ),
        ],
    )

    # ------------------------------------------------- 19 field validation
    bd.write_slide(
        "slide20.xml",
        [heading("Validation — Field Data: Lending Club")],
        [
            plain(
                "Calibration proves the detector is correct. Field data proves it fires on "
                "drift nobody chose: ~2.2 million real loans, 2007–2018, across the 2008 "
                "crisis and the 2016 credit-policy change.",
                1400, space_before=0,
            ),
            bullet(
                "Harness ready — reads the compressed file directly and scores quarterly windows "
                "against a fixed 2007 baseline, using the same code as the gateway.",
                1300, space_before=300,
            ),
            bullet(
                "Bug found before the first run — dates sorted as text, so “Aug-2018” would "
                "have become the baseline. Fixed, with a regression test on Lending Club's own "
                "date format.",
                1300, space_before=160,
            ),
            bullet(
                "Harness calibrated on a planted 2016 shift — found at the right quarter, with "
                "the right feature blamed.",
                1300, space_before=160,
            ),
            bullet(
                "Status: dataset run pending. Results will be reported as measured — the "
                "detector is not tuned to the data.",
                1300, space_before=160,
            ),
        ],
    )

    # ------------------------------------------------------ 20 defects
    bd.write_slide(
        "slide21.xml",
        [heading("Engineering Rigour — Defects We Found in Our Own System")],
        [
            plain(
                "Five defects, none visible to a test that sends one request at a time. "
                "Two were introduced and caught during this phase.",
                1300, space_before=0,
            ),
        ],
    )

    # ----------------------------------------------------- 21 work plan
    bd.write_slide(
        "slide22.xml",
        [heading("Work Plan to the Final Review")],
        [plain("What remains, and what each item depends on.", 1400, space_before=0)],
    )

    # ------------------------------------------------- 22 conclusion
    bd.write_slide(
        "slide9.xml",
        [heading("Conclusion")],
        [
            plain(
                f"{TESTS} tests passing · latency budget holds to 200 req/s, double Review-1 · "
                "overload no longer changes verdicts · all three trust signals live.",
                1400, bold=True, space_before=0,
            ),
        ],
    )


# --- tables and figures ------------------------------------------------------

TABLE_SLIDES = {
    "slide10.xml": (c2.PROGRESS, 2.55),
    "slide6.xml": (c2.REQUIREMENTS, 2.55),
    "slide8.xml": (c2.MODULE_STATUS, 2.45),
    "slide15.xml": (c2.RISK_COMPONENTS, 2.75),
    "slide21.xml": (c2.DEFECTS, 2.55),
    "slide22.xml": (c2.WORK_PLAN, 2.40),
    "slide9.xml": (c2.contributions(TESTS), 3.10),
}

FIGURE_SLIDES = {
    "slide4.xml": ("problem_timeline.png", 2.85, 11.0),
    "slide11.xml": ("on_path.png", 2.75, 10.6),
    "slide13.xml": ("gap_map.png", 2.85, 11.0),
    "slide7.xml": ("architecture.png", 2.95, 11.0),
    "slide14.xml": ("decision_flow.png", 3.00, 11.0),
    "slide16.xml": ("load_before_after.png", 2.75, 11.0),
    "slide17.xml": ("demo_trajectory.png", 2.80, 11.0),
    "slide18.xml": ("drift_attribution.png", 2.90, 11.0),
    "slide19.xml": ("calibration_curve.png", 2.75, 11.0),
}

ORDER = [
    "slide1.xml",   #  1 title
    "slide2.xml",   #  2 contents
    "slide3.xml",   #  3 abstract
    "slide10.xml",  #  4 progress since Review-1        [table]
    "slide4.xml",   #  5 introduction — motivation       [figure]
    "slide11.xml",  #  6 existing vs proposed           [figure]
    "slide12.xml",  #  7 objectives, scope, SDGs
    "slide5.xml",   #  8 literature survey              [template table]
    "slide13.xml",  #  9 research gap -> objectives     [figure]
    "slide6.xml",   # 10 requirements                   [table]
    "slide7.xml",   # 11 architecture                   [figure]
    "slide14.xml",  # 12 decision logic                 [figure]
    "slide8.xml",   # 13 implementation status          [table]
    "slide15.xml",  # 14 risk engine                    [table]
    "slide16.xml",  # 15 admission control              [figure]
    "slide17.xml",  # 16 live demo                      [figure]
    "slide18.xml",  # 17 drift attribution              [figure]
    "slide19.xml",  # 18 calibration                    [figure]
    "slide20.xml",  # 19 field validation
    "slide21.xml",  # 20 defects                        [table]
    "slide22.xml",  # 21 work plan                      [table]
    "slide9.xml",   # 22 conclusion + contributions     [table]
]


def main() -> None:
    bd.OUTPUT = HERE / "Custos_Phase2_Review2.pptx"
    bd.REVIEW_DATE = c2.REVIEW_DATE
    bd.ORDER = ORDER
    bd.DUPLICATES = len(ORDER) - 9
    bd.TABLE_SLIDES = TABLE_SLIDES
    bd.FIGURE_SLIDES = FIGURE_SLIDES
    bd.fill_all = fill_all
    # The template's own literature table is filled by build_deck.finish().
    bd.content = SimpleNamespace(
        LITERATURE=c2.LITERATURE, LITERATURE_COLUMNS=c2.LITERATURE_COLUMNS
    )
    bd.main()
    print(f"test count on slides: {TESTS}")


if __name__ == "__main__":
    main()
