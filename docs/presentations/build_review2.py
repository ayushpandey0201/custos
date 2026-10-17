"""Build the Phase-2 Review-2 deck — 15 slides — from the department template.

    python docs/presentations/make_figures.py
    python docs/presentations/build_review2.py

Short by design: bullets, at most one line of explanation, a figure wherever a
figure says it better. The full design is on the dashboard's "Inside Custos"
page, and the 25-slide version is kept reproducible in
build_review2_detailed.py for questions that go deeper.

Covers every section the template requires — title, contents, abstract,
introduction (overview, motivation, objectives, scope, SDGs, existing vs
proposed, work plan), literature survey with gap mapping, requirements, design,
implementation and conclusion.
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

# One size for every bullet, large enough for the back of a room.
B = 1700
LINE = 1500  # the single explanatory line under a heading


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


def line(text: str) -> str:
    """The one line of explanation a slide is allowed."""
    return plain(text, LINE, italic=True, space_before=0)


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
            plain("Decide  ·  Explain  ·  Record  ·  Heal", 1500, italic=True,
                  align="ctr", space_before=120),
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
            bullet("Abstract", B, space_before=0),
            bullet("Introduction — motivation, existing vs proposed, objectives", B),
            bullet("Literature survey and research gap", B),
            bullet("Requirement analysis and specification", B),
            bullet("System design — architecture and decision logic", B),
            bullet("Implementation and results", B),
            bullet("Governed self-healing and other domains", B),
            bullet("Conclusion and work plan  ·  then a live demo", B),
        ],
    )

    # ------------------------------------------------------------- 3 abstract
    bd.write_slide(
        "slide3.xml",
        [heading("Abstract")],
        [
            bullet("Models are validated once, then trusted forever — and fail quietly.", B,
                   space_before=0),
            bullet("Custos checks every model-driven action before it runs: "
                   "ALLOW, REVIEW or BLOCK.", B),
            bullet("It fuses policy rules, request risk and model drift — in under 50 ms.", B),
            bullet("Every verdict is explained, and hash-chained so it can't be quietly edited.",
                   B),
            bullet("It repairs a broken data feed — only after a person approves.", B),
            bullet(f"Validated: {TESTS} tests, load-tested, a pre-registered study on "
                   "589,186 real loans.", B),
        ],
    )

    # -------------------------------------------- 4 overview and motivation
    bd.write_slide(
        "slide4.xml",
        [heading("Introduction — Overview and Motivation")],
        [line("Models don't crash. They go quietly wrong — Zillow wrote off $304M in one "
              "quarter.")],
    )

    # ---------------------------------------------- 5 existing vs proposed
    bd.write_slide(
        "slide10.xml",
        [heading("Existing System vs Proposed System")],
        [line("Monitoring reports after the fact. Custos decides before the action.")],
    )

    # ------------------------------------- 6 objectives, scope and SDGs
    bd.write_slide(
        "slide11.xml",
        [heading("Objectives, Scope and SDGs")],
        [
            plain("Objectives", 1700, bold=True, space_before=0),
            bullet("Check drift on the live request path, within 50 ms", 1500, space_before=100),
            bullet("Name the inputs that moved", 1500, space_before=60),
            bullet("One explainable verdict from policy, risk and drift", 1500, space_before=60),
            bullet("A tamper-evident record of every verdict", 1500, space_before=60),
            bullet("Correct under overload; repairs only with human approval", 1500,
                   space_before=60),
            plain("Scope", 1700, bold=True, space_before=240),
            bullet("Gates any model-driven action. Never trains or retrains models.", 1500,
                   space_before=100),
            plain("SDGs", 1700, bold=True, space_before=240),
            bullet("9 Industry & innovation  ·  10 Fairer credit  ·  16 Accountable "
                   "institutions", 1500, space_before=100),
        ],
    )

    # ---------------------------------------------------- 7 literature survey
    bd.write_slide(
        "slide5.xml",
        [heading("Literature Survey")],
        [line("Every paper detects or diagnoses. None acts on the decision in flight.")],
    )

    # ------------------------------------------------------- 8 research gap
    bd.write_slide(
        "slide12.xml",
        [heading("Research Gap → Objectives")],
        [line("Each gap the survey found maps to one objective.")],
    )

    # ------------------------------------------------------- 9 requirements
    bd.write_slide(
        "slide6.xml",
        [heading("Requirement Analysis and Specification")],
        [line("What Custos must do — and the guarantees it must keep while doing it.")],
    )

    # ------------------------------------------------------ 10 architecture
    bd.write_slide(
        "slide7.xml",
        [heading("System Design — Architecture")],
        [line("The hot path answers every request; slow work runs offline. Full design: "
              "“Inside Custos”.")],
    )

    # ---------------------------------------------------- 11 decision logic
    bd.write_slide(
        "slide13.xml",
        [heading("System Design — Decision Logic")],
        [line("Rules before score: a veto always wins; a drifted model never auto-approves.")],
    )

    # ---------------------------------------------------- 12 implementation
    bd.write_slide(
        "slide8.xml",
        [heading("Implementation")],
        [line(f"{TESTS} tests  ·  p99 31 ms at 200 req/s  ·  0 verdicts changed by overload")],
    )

    # ------------------------------------------------------- 13 field result
    bd.write_slide(
        "slide14.xml",
        [heading("Results — Field Study on Real Loans")],
        [line("Pre-registered. Drift gating lost to random review — so the next gate ranks "
              "by risk.")],
    )

    # --------------------------------------- 14 self-healing and domains
    bd.write_slide(
        "slide15.xml",
        [heading("Governed Self-Healing — and Beyond Lending")],
        [line("Same engine, any domain: AI agents · pricing · triage · hiring · claims.")],
    )

    # ------------------------------------------------------- 15 conclusion
    bd.write_slide(
        "slide9.xml",
        [heading("Conclusion and Work Plan")],
        [
            bullet("Custos gates any model-driven action — decides, explains, records, heals.",
                   1600, space_before=0),
            bullet("Next: risk-ranked review · a second dataset · scale-out on PostgreSQL.",
                   1600, space_before=120),
            bullet("Now: a live demo — three scenarios, two domains.", 1600, space_before=120),
            # The line the deck ends on, and the two lines that carry it.
            plain("Models decide. Custos makes sure they still deserve to.", 2600,
                  bold=True, align="ctr", space_before=600),
            plain("“A model that is running is not a model that can be trusted.", 1600,
                  italic=True, align="ctr", space_before=300),
            plain("Custos checks the difference — every decision, every time.”", 1600,
                  italic=True, align="ctr", space_before=0),
        ],
    )


# --- tables and figures ------------------------------------------------------

# (spec, top in inches, font in points)
TABLE_SLIDES = {
    "slide6.xml": (c2.REQUIREMENTS_SHORT, 2.30, 14.0),
    "slide8.xml": (c2.STATUS_SHORT, 2.30, 14.0),
    "slide9.xml": (c2.CONTRIBUTIONS_SHORT, 4.6, 13.0),
}

FIGURE_SLIDES = {
    "slide4.xml": ("problem_timeline.png", 2.45, 11.0),
    "slide10.xml": ("on_path.png", 2.40, 10.6),
    "slide12.xml": ("gap_map.png", 2.45, 11.0),
    "slide7.xml": ("architecture.png", 2.45, 11.0),
    "slide13.xml": ("decision_flow.png", 2.60, 11.0),
    "slide14.xml": ("gating_results.png", 2.40, 11.0),
    "slide15.xml": ("self_healing_loop.png", 2.80, 11.0),
}

ORDER = [
    "slide1.xml",   #  1 title
    "slide2.xml",   #  2 contents
    "slide3.xml",   #  3 abstract
    "slide4.xml",   #  4 overview and motivation        [figure]
    "slide10.xml",  #  5 existing vs proposed           [figure]
    "slide11.xml",  #  6 objectives, scope, SDGs
    "slide5.xml",   #  7 literature survey              [template table]
    "slide12.xml",  #  8 research gap -> objectives     [figure]
    "slide6.xml",   #  9 requirements                   [table]
    "slide7.xml",   # 10 architecture                   [figure]
    "slide13.xml",  # 11 decision logic                 [figure]
    "slide8.xml",   # 12 implementation status          [table]
    "slide14.xml",  # 13 field study result             [figure]
    "slide15.xml",  # 14 self-healing + domains         [figure]
    "slide9.xml",   # 15 conclusion, work plan, team    [table]
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
        LITERATURE=c2.LITERATURE_SHORT, LITERATURE_COLUMNS=c2.LITERATURE_COLUMNS
    )
    bd.main()
    print(f"test count on slides: {TESTS}")


if __name__ == "__main__":
    main()
