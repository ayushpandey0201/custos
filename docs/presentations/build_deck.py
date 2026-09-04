"""Build the Phase-2 Review-1 deck from the department's .pptx template.

    python docs/presentations/build_deck.py

Regenerates `Custos_Phase2_Review1.pptx` end to end: unpack the template,
duplicate its content slide as many times as the narrative needs, put the slides
in order, fill every title and body, fill the literature-survey table, and place
the two figures.

Written as a script rather than done by hand because the deck has to be rebuilt
for each review. Editing 20 slides by hand once is tedious; doing it again in a
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

REVIEW_DATE = "4 September 2026"


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


def fill_all() -> None:
    write_slide(
        "slide1.xml",
        [
            plain("BMS College of Engineering", 2800, bold=True, align="ctr", space_before=0),
            plain("(Autonomous College under VTU)", 1400, align="ctr", space_before=100),
            plain(
                "Department of Artificial Intelligence and Data Science",
                1600, bold=True, align="ctr", space_before=200,
            ),
            plain(
                "Project Work Phase-II (23AI7PWPP1) — Review-1 Presentation on",
                1400, align="ctr", space_before=300,
            ),
            plain(
                "Custos: A Runtime Trust Layer for AI Agents",
                2400, bold=True, align="ctr", space_before=300,
            ),
            plain("and Machine Learning Models", 2400, bold=True, align="ctr", space_before=0),
        ],
        [
            plain("Presented by", 1300, italic=True, align="ctr", space_before=0),
            plain("«Student Name 1»\t\t«USN»", 1600, bold=True, align="ctr", space_before=200),
            plain("«Student Name 2»\t\t«USN»", 1600, bold=True, align="ctr", space_before=100),
            plain("«Student Name 3»\t\t«USN»", 1600, bold=True, align="ctr", space_before=100),
            plain("Under the guidance of", 1300, italic=True, align="ctr", space_before=400),
            plain("«Guide Name»", 1600, bold=True, align="ctr", space_before=150),
            plain("«Designation», Dept. of AI & DS", 1400, align="ctr", space_before=50),
        ],
    )

    write_slide(
        "slide2.xml",
        [heading("Table of Contents")],
        [
            bullet("Abstract", 1700),
            bullet("Introduction — overview, motivation, objectives, scope, SDGs, work plan", 1700),
            bullet("Literature Survey, research gap and mapping to objectives", 1700),
            bullet("Requirement Analysis and Specification", 1700),
            bullet(
                "System Design — architecture, request flow, all modules, drift pipeline, "
                "decision cascade, data model, key decisions",
                1700,
            ),
            bullet("Implementation — module status, API surface, engine internals", 1700),
            bullet("Results — live demonstration and drift attribution", 1700),
            bullet("Testing, team contributions, conclusion and Review-2 plan", 1700),
        ],
    )

    write_slide(
        "slide3.xml",
        [heading("Abstract")],
        [
            plain(
                "Machine learning models are deployed once and then trusted indefinitely. Serving "
                "infrastructure reports that a model is running; nothing in a typical production "
                "stack reports whether it is still reliable at the moment a decision is made.",
                1600, space_before=0,
            ),
            plain(
                "Custos is a runtime trust layer that sits between an AI agent and its consequential "
                "action. On every request it fuses three independent signals — policy compliance, "
                "feature-distribution drift, and contextual risk — into a single weighted trust "
                "score, and converts that score into one of three verdicts: ALLOW, REVIEW or BLOCK.",
                1600,
            ),
            plain(
                "Drift is quantified offline using PSI and the Kolmogorov–Smirnov statistic against "
                "a baseline fixed at model registration, keeping the request path within a 50 ms "
                "p99 budget. Every verdict is written to a per-tenant SHA-256 hash chain, making "
                "any later modification of the decision record detectable and localisable.",
                1600,
            ),
            plain(
                "A working system has been implemented and demonstrated end-to-end on a fintech "
                "credit-underwriting scenario, in which an unchanged model and unchanged code move "
                "from ALLOW to REVIEW to BLOCK purely because the incoming population shifted.",
                1600,
            ),
        ],
    )

    write_slide(
        "slide4.xml",
        [heading("Introduction — Overview and Motivation")],
        [
            plain("Overview", 1800, bold=True, space_before=0),
            bullet(
                "Custos is an enforcement layer, not a dashboard. It returns a blocking verdict on "
                "the request path, before an irreversible action is taken.", 1500,
            ),
            bullet(
                "One question, answered per request: given what is currently known about this model "
                "and this input, should this action proceed?", 1500,
            ),
            plain("Motivation", 1800, bold=True, space_before=500),
            bullet(
                "monitoring is periodic, damage is immediate. Practitioner interviews conducted for "
                "this project confirmed that PSI/CSI reports are produced quarterly, while an "
                "incorrect automated approval loses money the same day.",
                1500, bold_prefix="Timing gap — ",
            ),
            bullet(
                "most production incidents are not model decay but broken feature pipelines, where "
                "a feature silently pins to a constant. The two require opposite responses.",
                1500, bold_prefix="Attribution gap — ",
            ),
            bullet(
                "in lending, a wrong decision is a direct financial loss, so full autonomy is "
                "unacceptable and full manual review is unaffordable. A third verdict is required.",
                1500, bold_prefix="Autonomy gap — ",
            ),
            plain(
                "Grounded in primary interviews with production credit-risk practitioners "
                "(docs/conversations/).", 1300, italic=True, space_before=400,
            ),
        ],
    )

    write_slide(
        "slide10.xml",
        [heading("Introduction — Objectives and Scope")],
        [
            plain("Objectives", 1800, bold=True, space_before=0),
            bullet("Fuse multiple independent trust signals into one blocking runtime decision.", 1500, bold_prefix="O1  "),
            bullet("Quantify feature drift per model and attribute it to individual features.", 1500, bold_prefix="O2  "),
            bullet("Keep the enforcement path within a 50 ms p99 latency budget.", 1500, bold_prefix="O3  "),
            bullet("Produce a tamper-evident audit record for every decision.", 1500, bold_prefix="O4  "),
            bullet("Make the system extensible — a new signal must be an additive change.", 1500, bold_prefix="O5  "),
            bullet("Keep integration effort to five lines or fewer of caller code.", 1500, bold_prefix="O6  "),
            plain("Scope", 1800, bold=True, space_before=450),
            bullet(
                "policy rule evaluation, drift detection and scoring, signal fusion, decision "
                "enforcement, audit chain, multi-tenant configuration, operator dashboard.",
                1500, bold_prefix="In scope: ",
            ),
            bullet(
                "Custos does not train, serve or host models; it does not explain individual "
                "predictions; it does not retrain or roll back. It decides and records — humans act.",
                1500, bold_prefix="Out of scope: ",
            ),
        ],
    )

    write_slide(
        "slide11.xml",
        [heading("Introduction — Existing vs. Proposed System")],
        [
            plain("Existing systems and what they leave unanswered", 1800, bold=True, space_before=0),
            bullet(
                "Evidently AI, WhyLabs, Arize — detect drift offline and report it on a dashboard. "
                "They cannot block a request.", 1450, bold_prefix="Model monitoring: ",
            ),
            bullet(
                "Open Policy Agent, API gateways — enforce authorisation, but know nothing about "
                "whether a model is still statistically reliable.", 1450, bold_prefix="Policy engines: ",
            ),
            bullet(
                "MLflow, SageMaker, Vertex AI — confirm a model is deployed and healthy, not that "
                "it is still trustworthy for the population it now sees.", 1450, bold_prefix="MLOps platforms: ",
            ),
            bullet(
                "record the inputs used, but not whether those inputs still resemble training data.",
                1450, bold_prefix="Feature stores: ",
            ),
            plain("Proposed system", 1800, bold=True, space_before=450),
            bullet(
                "Custos fuses drift, policy and risk into a single enforceable verdict on the "
                "request path, with per-feature attribution and a cryptographically verifiable "
                "audit trail.", 1450,
            ),
            plain(
                "The components exist separately. What does not exist is a layer that fuses them "
                "into one blocking decision and can prove afterwards what it decided and why.",
                1400, italic=True, space_before=400,
            ),
        ],
    )

    write_slide(
        "slide12.xml",
        [heading("Introduction — SDG Alignment and Work Plan")],
        [
            plain("Sustainable Development Goals", 1800, bold=True, space_before=0),
            bullet(
                "Industry, Innovation and Infrastructure — builds resilient, auditable "
                "infrastructure for automated decision systems.", 1450, bold_prefix="SDG 9: ",
            ),
            bullet(
                "Reduced Inequalities — blocking a model that has drifted away from the population "
                "it was trained on directly limits systematically unfair automated credit decisions.",
                1450, bold_prefix="SDG 10: ",
            ),
            bullet(
                "Peace, Justice and Strong Institutions — tamper-evident decision records support "
                "accountability and regulatory audit of automated decisions.", 1450, bold_prefix="SDG 16: ",
            ),
            plain("Work plan", 1800, bold=True, space_before=450),
            bullet("Problem study, practitioner interviews, literature survey, architecture and ADRs. — completed", 1450, bold_prefix="Phase 1: "),
            bullet("Contract layer, drift engine, policy engine, trust engine, audit chain. — completed", 1450, bold_prefix="Phase 2a: "),
            bullet("Gateway and control plane APIs, Python SDK, dashboard, fintech demo. — completed", 1450, bold_prefix="Phase 2b: "),
            bullet("Risk engine, latency benchmarking at scale, deployment hardening. — in progress", 1450, bold_prefix="Phase 2c: "),
        ],
    )

    write_slide(
        "slide5.xml",
        [heading("Literature Survey")],
        [
            plain(
                "Surveyed across three areas: distribution-shift detection, policy enforcement for "
                "ML systems, and tamper-evident audit logging.", 1500, space_before=0,
            )
        ],
    )

    write_slide(
        "slide13.xml",
        [heading("Research Gap and Mapping to Objectives")],
        [
            plain("Research gaps identified", 1800, bold=True, space_before=0),
            bullet(
                "Drift detection is universally treated as an offline, observational activity. No "
                "surveyed work places a drift statistic on the enforcement path of a live request.",
                1450, bold_prefix="G1  ",
            ),
            bullet(
                "Drift is reported as a single model-level number; the surveyed tools do not "
                "distinguish a genuine population shift from an upstream pipeline failure.",
                1450, bold_prefix="G2  ",
            ),
            bullet(
                "Policy enforcement and model-reliability monitoring are separate systems that "
                "never contribute to a single decision.", 1450, bold_prefix="G3  ",
            ),
            bullet(
                "Decision logs are ordinary application logs — mutable, and therefore weak evidence "
                "under audit.", 1450, bold_prefix="G4  ",
            ),
            plain("Mapping of gaps to objectives", 1800, bold=True, space_before=400),
            bullet("G1 → O1, O3   drift moved onto the request path within a bounded latency budget", 1450),
            bullet("G2 → O2       per-feature PSI/KS attribution surfaced with every verdict", 1450),
            bullet("G3 → O1, O5   one engine interface, weighted fusion, registry-based extension", 1450),
            bullet("G4 → O4       SHA-256 hash chain with a verification endpoint", 1450),
        ],
    )

    write_slide(
        "slide6.xml",
        [heading("Requirement Analysis — Functional")],
        [
            bullet("The system shall register models per tenant and record a reference feature distribution.", 1450, bold_prefix="FR1  "),
            bullet("The system shall compute PSI and KS per feature against that baseline, offline.", 1450, bold_prefix="FR2  "),
            bullet("The system shall roll per-feature statistics into a single model severity in [0, 1].", 1450, bold_prefix="FR3  "),
            bullet("The system shall evaluate tenant-authored policy rules against request context.", 1450, bold_prefix="FR4  "),
            bullet("The system shall fuse enabled engine signals into a weighted trust score.", 1450, bold_prefix="FR5  "),
            bullet("The system shall return ALLOW, REVIEW or BLOCK with human-readable reasons.", 1450, bold_prefix="FR6  "),
            bullet("The system shall honour an engine veto irrespective of all other signals.", 1450, bold_prefix="FR7  "),
            bullet("The system shall append every decision to a per-tenant tamper-evident hash chain.", 1450, bold_prefix="FR8  "),
            bullet("The system shall verify a chain on demand and report the first modified entry.", 1450, bold_prefix="FR9  "),
            bullet("The system shall expose drift history and per-feature breakdown to an operator.", 1450, bold_prefix="FR10 "),
            bullet("The system shall allow per-tenant configuration of engines, weights and thresholds.", 1450, bold_prefix="FR11 "),
            bullet("The system shall route requests for unregistered models to REVIEW.", 1450, bold_prefix="FR12 "),
        ],
    )

    write_slide(
        "slide14.xml",
        [heading("Requirement Analysis — Non-Functional and Environment")],
        [
            plain("Non-functional requirements", 1800, bold=True, space_before=0),
            bullet("gateway p99 ≤ 50 ms; per-engine budget 20 ms, enforced by cancellation.", 1450, bold_prefix="NFR1 Latency: "),
            bullet("a Custos failure must not fail the caller — fail-open by default, overridable per tenant.", 1450, bold_prefix="NFR2 Availability: "),
            bullet("tenant_id on every table and every query; per-tenant audit chains.", 1450, bold_prefix="NFR3 Isolation: "),
            bullet("API keys stored only as SHA-256 digests; rule text parsed, never evaluated.", 1450, bold_prefix="NFR4 Security: "),
            bullet("adding a signal must not modify existing engines or services.", 1450, bold_prefix="NFR5 Extensibility: "),
            bullet("gateway and worker horizontally scalable; drift tasks idempotent.", 1450, bold_prefix="NFR6 Scalability: "),
            plain("Software and hardware environment", 1800, bold=True, space_before=400),
            bullet("Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic v2, Alembic, Celery.", 1450, bold_prefix="Backend: "),
            bullet("React 18, TypeScript 5, Vite 5.", 1450, bold_prefix="Frontend: "),
            bullet("PostgreSQL 16 and Redis 7 in production; SQLite and an in-process cache on a single node.", 1450, bold_prefix="Data: "),
            bullet("Docker Compose; runs unmodified on a standard laptop with no external services.", 1450, bold_prefix="Deployment: "),
        ],
    )

    # --- System design ------------------------------------------------------

    write_slide(
        "slide7.xml",
        [heading("System Design — Architecture")],
        [
            plain(
                "Two planes. The split is the load-bearing decision: the data plane does the "
                "minimum possible work per request, and everything expensive — statistics, "
                "validation, chain verification — lives on the control plane or in the worker.",
                1400, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide29.xml",
        [heading("System Design — Request Flow")],
        [
            plain(
                "One /v1/evaluate call, in the order it actually happens. Steps 2, 3 and 5 are "
                "cached reads; step 7 is pure computation; only steps 8 and 10 touch the database, "
                "and step 10 runs after the caller already has its answer.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide15.xml",
        [heading("System Design — Request Lifecycle")],
        [
            plain(
                "Nine steps inside a 50 ms p99 budget. Every read on this path is cached, and the "
                "only two steps that touch the database on a warm cache are the audit append and "
                "the background feature capture.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide16.xml",
        [heading("System Design — Modules: Contract Layer and Engine Seam")],
        [
            plain(
                "shared/ is imported by every service and no service defines its own copy of a "
                "shared type. engines/ is the extensibility seam — engines never import one another.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide17.xml",
        [heading("System Design — Modules: Policy, Drift and Risk Engines")],
        [
            plain(
                "Three signals behind one interface. All cross-engine flow passes through the Trust "
                "Engine, which is what makes adding a fourth signal a purely additive change.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide18.xml",
        [heading("System Design — Modules: Services, SDK and Dashboard")],
        [
            plain(
                "Services contain wiring, not logic. Every business decision lives in engines/ or "
                "shared/, so a service file can be read end to end without learning the domain.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide30.xml",
        [heading("System Design — Drift Pipeline")],
        [
            plain(
                "Where the statistics run, and where they do not. Everything expensive happens "
                "below the boundary on a schedule; the request path above it only ever reads a "
                "number the worker has already computed.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide19.xml",
        [heading("System Design — Decision Logic")],
        [
            plain(
                "Signals fuse as a weighted mean over non-degraded engines (policy 0.3, drift 0.5, "
                "risk 0.2), renormalised. A veto clamps the score to 0.0. The matrix below is then "
                "evaluated as an ordered cascade — the order is the specification.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide31.xml",
        [heading("System Design — Decision Cascade")],
        [
            plain(
                "The same matrix as a flow. Each condition is tested in turn; the first one that "
                "holds decides, and falling off the end is the only route to ALLOW.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide20.xml",
        [heading("System Design — Data Model")],
        [
            plain(
                "Seven tables, every one tenant-scoped. Two of them record every decision on "
                "purpose: the audit chain is the record of truth but expensive to read honestly, "
                "so a denormalised copy exists for the dashboard.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide21.xml",
        [heading("System Design — Key Design Decisions (ADRs)")],
        [
            plain(
                "Every irreversible decision is recorded as an Architecture Decision Record with "
                "its context, the decision, and the consequence accepted.",
                1350, space_before=0,
            ),
        ],
    )

    # --- Implementation -----------------------------------------------------

    write_slide(
        "slide8.xml",
        [heading("Implementation — Module Status")],
        [
            plain(
                "Ten of twelve components are complete and exercised end to end. The remaining two "
                "are deliberate: the risk engine is a wired seam, and the sidecar proxy is Review-2 "
                "scope.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide22.xml",
        [heading("Implementation — API Surface")],
        [
            plain(
                "Three endpoints on the hot data plane; fourteen on the cold control plane. All "
                "control-plane validation happens here so an incoherent configuration can never "
                "reach the request path.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide23.xml",
        [heading("Implementation — Drift Engine Internals")],
        [
            plain("Detectors — pure standard-library Python, no NumPy or SciPy", 1650, bold=True, space_before=0),
            bullet(
                "PSI = Σ (aᵢ − eᵢ) · ln(aᵢ / eᵢ) over equal-frequency buckets drawn from the "
                "reference sample. Equal-frequency because credit features are heavily skewed and "
                "equal-width bucketing puts nearly all the mass in one bucket.", 1400,
            ),
            bullet(
                "KS = max |CDF_expected − CDF_actual|, computed in a single merge pass. Bucket-free, "
                "so it catches shifts that fall inside a PSI bucket.", 1400,
            ),
            bullet(
                "Neither returns a p-value: on production volumes every distribution differs "
                "significantly, so effect size is what is operationally meaningful.", 1400,
            ),
            bullet(
                "Both raise on an empty sample rather than returning 0.0 — absence of evidence must "
                "never be reported as evidence of stability.", 1400,
            ),
            plain("Severity roll-up", 1650, bold=True, space_before=350),
            bullet(
                "Per feature: PSI mapped through the industry bands (0.10 → 0.33, 0.25 → 0.66, "
                "0.50 → 1.00). KS may only raise a feature's severity, never lower it.", 1400,
            ),
            bullet(
                "Across features: 0.6 · max + 0.4 · mean. Pure max lets one noisy feature dominate; "
                "pure mean lets fifty stable features bury one dead pipeline.", 1400,
            ),
            bullet(
                "Both max and mean are monotone non-decreasing, so any convex combination is too — "
                "the invariant that worse drift can never yield lower severity holds by construction, "
                "not by testing.", 1400,
            ),
            plain(
                "Baselines are fixed at registration, never rolling: comparing each window to the "
                "previous one makes slow drift invisible.", 1300, italic=True, space_before=300,
            ),
        ],
    )

    write_slide(
        "slide24.xml",
        [heading("Implementation — Audit and Evidence Chain")],
        [
            plain("entry_hash = SHA-256( prev_hash ‖ canonical_json(payload) )", 1600, bold=True, space_before=0),
            bullet(
                "Per-tenant chains with contiguous sequence numbers and a genesis prev_hash of "
                "sixty-four zeros. Payloads serialise with sorted keys, so a given payload always "
                "hashes identically.", 1400,
            ),
            bullet(
                "The claim is tamper-evidence, not tamper-proofing. Anyone with database access can "
                "rewrite a row; what they cannot do is rewrite one without invalidating every hash "
                "after it.", 1400,
            ),
            plain("Three attacks, three outcomes", 1600, bold=True, space_before=350),
            bullet("Edit a payload → the hash no longer matches at that entry.", 1400),
            bullet(
                "Edit a payload and recompute its hash → the successor's prev_hash no longer links, "
                "so the break surfaces one entry later.", 1400,
            ),
            bullet("Delete an entry → a sequence gap.", 1400),
            plain(
                "GET /audit/verify recomputes the chain and reports the first broken sequence "
                "number, which localises tampering rather than merely detecting it. Raw feature "
                "values are deliberately excluded from the payload — that is the caller's customer "
                "data, and an append-only log is the last place it should be duplicated.",
                1400, space_before=350,
            ),
        ],
    )

    # --- Results ------------------------------------------------------------

    write_slide(
        "slide25.xml",
        [heading("Results — Live Demonstration")],
        [
            plain(
                "A lending agent auto-approves loan applications using a credit-risk model. Custos "
                "gates the disbursement. One command, no external infrastructure.",
                1500, space_before=0,
            ),
            bullet("Model never registered → REVIEW. Custos escalates rather than guessing.", 1400, bold_prefix="Act 1  "),
            bullet("Registered and baselined on 600 applications, healthy traffic → ALLOW, trust 0.99, drift severity 0.021.", 1400, bold_prefix="Act 2  "),
            bullet(
                "Population shifts — incomes fall, utilisation spikes. Drift severity 0.021 → 0.830, "
                "attributed per feature (next slide).", 1400, bold_prefix="Act 3  ",
            ),
            bullet(
                "The same application and the same code → REVIEW, trust 0.48. The verdict changed "
                "because the world changed — no redeploy, no configuration edit.",
                1400, bold_prefix="Act 4  ",
            ),
            bullet(
                "A 900,000 disbursement against a 500,000 policy rule → BLOCK, trust 0.00. The "
                "audit chain verifies across 604 entries; editing one BLOCK record to read ALLOW is "
                "detected and localised to entry #604.", 1400, bold_prefix="Act 5  ",
            ),
            plain("Measured gateway p99 across the demonstration run: 0.5 ms, against a 50 ms budget.", 1450, bold=True, space_before=400),
        ],
    )

    write_slide(
        "slide26.xml",
        [heading("Results — Drift Attribution")],
        [
            plain(
                "Severity alone says a model has moved. The per-feature breakdown says which input "
                "moved — which is what decides whether this is a real population shift or a broken "
                "upstream feed.",
                1400, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide27.xml",
        [heading("Testing")],
        [
            plain(
                "268 tests, all passing. The suite is written against the properties that must hold, "
                "not against the implementation — golden values, invariants, and every row of the "
                "decision matrix.",
                1350, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide28.xml",
        [heading("Team Contributions")],
        [
            plain(
                "Work was split along the module boundaries described in the System Design section, "
                "so each member owns a vertical slice with its own tests.",
                1400, space_before=0,
            ),
        ],
    )

    write_slide(
        "slide9.xml",
        [heading("Conclusion")],
        [
            plain(
                "A working runtime trust layer has been built and demonstrated end to end. An "
                "unchanged model and unchanged caller code move from ALLOW to REVIEW to BLOCK "
                "purely because the incoming population changed — which is the behaviour the "
                "project set out to produce.",
                1500, space_before=0,
            ),
            plain("Objectives achieved", 1650, bold=True, space_before=350),
            bullet("O1, O5 — multi-signal fusion behind one extensible engine interface.", 1400),
            bullet("O2 — per-feature PSI/KS attribution surfaced with every verdict.", 1400),
            bullet("O3 — measured gateway p99 of 0.5 ms against a 50 ms budget.", 1400),
            bullet("O4 — tamper-evident audit chain, demonstrated under an actual tampering attempt.", 1400),
            bullet("O6 — five-line integration surface, standard library only.", 1400),
            plain("Remaining work for Review-2", 1650, bold=True, space_before=350),
            bullet("Implement the risk engine behind the existing seam (transaction velocity, anomaly scoring).", 1400),
            bullet("Load-test the gateway under concurrency and validate the p99 budget at realistic volume.", 1400),
            bullet("Separate pipeline-break detection from population shift as an explicit signal.", 1400),
            bullet("Language-agnostic sidecar proxy so non-Python callers can integrate.", 1400),
        ],
    )


# --- tables and figures (python-pptx, after repacking) ----------------------

# Keyed by slide *file*, not by position. Position changes whenever a slide is
# inserted, and a stale index silently drops a table onto the wrong slide —
# which is a mistake that survives validation and only shows up when someone
# reads the deck. ORDER is the single place slide sequence is declared.
TABLE_SLIDES = {
    "slide15.xml": (content.REQUEST_LIFECYCLE, 2.85),
    "slide16.xml": (content.MODULES_CONTRACT, 2.75),
    "slide17.xml": (content.MODULES_ENGINES, 2.75),
    "slide18.xml": (content.MODULES_SERVICES, 2.70),
    "slide19.xml": (content.DECISION_MATRIX, 2.95),
    "slide20.xml": (content.DATA_MODEL, 2.95),
    "slide21.xml": (content.DECISIONS, 2.80),
    "slide8.xml": (content.MODULE_STATUS, 2.80),
    "slide22.xml": (content.API_SURFACE, 2.90),
    "slide27.xml": (content.TEST_COVERAGE, 2.80),
    "slide28.xml": (content.CONTRIBUTIONS, 2.90),
}

FIGURE_SLIDES = {
    "slide7.xml": ("architecture.png", 3.0, 11.0),
    # Narrower, because the sequence diagram is the tallest figure in the deck
    # and scaling the width down is what keeps its foot clear of the footer.
    "slide29.xml": ("request_flow.png", 2.50, 10.6),
    "slide30.xml": ("drift_pipeline.png", 3.05, 11.0),
    "slide31.xml": ("decision_flow.png", 3.10, 11.0),
    "slide26.xml": ("drift_attribution.png", 3.0, 11.0),
}

SLIDE_WIDTH_IN = 13.333
TABLE_LEFT_IN = 1.05
TABLE_WIDTH_IN = 11.2
HEADER_FILL = "1F5CA8"
ZEBRA_FILL = "F4F6F9"


def _style_cell(cell, text, size, bold=False, colour=None, fill=None):
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    cell.margin_left = cell.margin_right = Pt(4)
    cell.margin_top = cell.margin_bottom = Pt(2)
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


def add_table(slide, spec, top_in: float, font_pt: float = 10.0) -> None:
    """Place a documented table below the slide's intro text.

    Row heights are set to the minimum PowerPoint honours; it grows any row
    whose text needs more, so setting them small keeps the table as short as
    its content allows instead of padding every row to a fixed height.
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
    table.horz_banding = False  # banding is applied explicitly below

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
    slide = prs.slides[7]
    shape = next(sh for sh in slide.shapes if sh.has_table)
    shape.left, shape.top, shape.width = Inches(1.05), Inches(2.55), Inches(11.2)
    for col, frac in zip(shape.table.columns, content.LITERATURE_COLUMNS, strict=True):
        col.width = Emu(int(Inches(11.2) * frac))

    for r, values in enumerate(content.LITERATURE, start=1):
        for c, text in enumerate(values):
            para = shape.table.cell(r, c).text_frame.paragraphs[0]
            for existing in list(para.runs):
                existing._r.getparent().remove(existing._r)
            cell_run = para.add_run()
            cell_run.text = text
            cell_run.font.size = Pt(9.5)
            cell_run.font.name = "Calibri"
    for c in range(6):
        for para in shape.table.cell(0, c).text_frame.paragraphs:
            for header_run in para.runs:
                header_run.font.size = Pt(10.5)
                header_run.font.bold = True

    # -- generated tables --
    for slide_file, (spec, top_in) in TABLE_SLIDES.items():
        rows = len(spec[1])
        # Long tables get a point smaller so they stay clear of the footer.
        add_table(prs.slides[ORDER.index(slide_file)], spec, top_in, font_pt=9.0 if rows >= 10 else 10.0)

    # -- figures, centred horizontally: (13.333 - 11.0) / 2 --
    for slide_file, (name, top_in, width_in) in FIGURE_SLIDES.items():
        left_in = (SLIDE_WIDTH_IN - width_in) / 2
        prs.slides[ORDER.index(slide_file)].shapes.add_picture(
            str(FIGURES / name), Inches(left_in), Inches(top_in), width=Inches(width_in)
        )

    prs.save(str(path))


# --- orchestration ---------------------------------------------------------

ORDER = [
    "slide1.xml",   # 1  title
    "slide2.xml",   # 2  contents
    "slide3.xml",   # 3  abstract
    "slide4.xml",   # 4  introduction — overview and motivation
    "slide10.xml",  # 5  introduction — objectives and scope
    "slide11.xml",  # 6  introduction — existing vs proposed
    "slide12.xml",  # 7  introduction — SDGs and work plan
    "slide5.xml",   # 8  literature survey (template table)
    "slide13.xml",  # 9  research gap and mapping
    "slide6.xml",   # 10 requirements — functional
    "slide14.xml",  # 11 requirements — non-functional and environment
    "slide7.xml",   # 12 design — architecture               [figure]
    "slide29.xml",  # 13 design — request flow               [figure]
    "slide15.xml",  # 14 design — request lifecycle          [table]
    "slide16.xml",  # 14 design — modules: contract + seam   [table]
    "slide17.xml",  # 15 design — modules: engines           [table]
    "slide18.xml",  # 17 design — modules: services and SDK  [table]
    "slide30.xml",  # 18 design — drift pipeline             [figure]
    "slide19.xml",  # 19 design — decision logic             [table]
    "slide31.xml",  # 20 design — decision cascade           [figure]
    "slide20.xml",  # 21 design — data model                 [table]
    "slide21.xml",  # 19 design — key decisions (ADRs)       [table]
    "slide8.xml",   # 20 implementation — module status      [table]
    "slide22.xml",  # 21 implementation — API surface        [table]
    "slide23.xml",  # 22 implementation — drift internals
    "slide24.xml",  # 23 implementation — audit chain
    "slide25.xml",  # 24 results — live demonstration
    "slide26.xml",  # 25 results — drift attribution         [figure]
    "slide27.xml",  # 26 testing                             [table]
    "slide28.xml",  # 27 team contributions                  [table]
    "slide9.xml",   # 28 conclusion
]

# Template ships 9 slides; the rest are clones of its plain content slide.
DUPLICATES = len(ORDER) - 9


def main() -> None:
    if not TEMPLATE.exists():
        raise SystemExit(f"template not found: {TEMPLATE}")
    if not (FIGURES / "architecture.png").exists():
        raise SystemExit("figures missing — run docs/presentations/make_figures.py first")

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    with zipfile.ZipFile(TEMPLATE) as z:
        z.extractall(WORK)

    # Structural work first: duplicating a slide copies it verbatim, so any
    # content written before this point would be cloned along with it.
    unknown = (set(TABLE_SLIDES) | set(FIGURE_SLIDES)) - set(ORDER)
    if unknown:
        raise AssertionError(f"table/figure targets not in ORDER: {sorted(unknown)}")

    duplicate_slides(DUPLICATES)
    reorder(ORDER)
    fill_all()

    OUTPUT.unlink(missing_ok=True)
    subprocess.run(["zip", "-Xrq", str(OUTPUT), "."], cwd=WORK, check=True, capture_output=True)
    finish(OUTPUT)
    shutil.rmtree(WORK, ignore_errors=True)

    print(f"built {OUTPUT.name} — {len(ORDER)} slides, {len(TABLE_SLIDES) + 1} tables, {len(FIGURE_SLIDES)} figures")


if __name__ == "__main__":
    main()
