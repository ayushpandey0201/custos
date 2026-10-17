import type { TourStep } from "./Tour";

/* What the guide says on each page. Written for two readers at once: a client
 * using Custos for the first time, and a presenter explaining the screen to a
 * reviewer — so each step says what the thing is and why it matters. */

const SWITCHER: TourStep = {
  target: "switcher",
  title: "Three demos, one sequence",
  body:
    "Run them in order, about ten minutes in all: 1 — a lending model drifts and Custos stops trusting it; 2 — a data feed breaks and Custos repairs it once a person approves; 3 — the same Custos guarding an AI agent in a different business. The highlighted card is where you are.",
};

const SYSCHECK: TourStep = {
  target: "syscheck",
  title: "Is the system up? Then start here",
  body:
    "Green means the gateway and control plane are running. The “Start the demo” button sits right here. If the light is red, run ./app.sh in a terminal and wait a few seconds.",
};

const STEPPER: TourStep = {
  target: "stepper",
  title: "The steps",
  body:
    "Steps unlock one at a time, because each builds on the last. Clicking a tab only selects it and takes you to its card — the button that runs the step is in the card.",
};

const SAY: TourStep = {
  target: "say",
  title: "Say this",
  body:
    "Read this aloud while the step runs. When the result appears, a “Point at this” box tells you exactly what to show the audience.",
};

export const TOURS: Record<string, TourStep[]> = {
  home: [
    {
      title: "Welcome to Custos",
      body:
        "A one-minute tour of this page. Use the buttons or the arrow keys; Esc leaves at any time. You can start this guide again from the “Guide me” button on every page.",
    },
    {
      target: "hero",
      title: "What Custos is",
      body:
        "A checkpoint between a machine-learning model and the action it triggers — a loan, a refund, a payment. Before the action runs, Custos answers: ALLOW it, send it to a human (REVIEW), or BLOCK it.",
    },
    {
      target: "stats",
      title: "The evidence, in four numbers",
      body:
        "All measured in this repository: decision latency under load, verdicts changed by overload (none), the automated test suite, and the 589,186 real loans in our pre-registered field study.",
    },
    {
      target: "problem",
      title: "The problem it solves",
      body:
        "Models don't crash — they go quietly wrong as the world changes. Zillow's pricing model kept making offers as the market moved, until a $304M write-down. Checks happen quarterly; decisions happen every second.",
    },
    {
      target: "compare",
      title: "How Custos is different",
      body:
        "Monitoring reports after the fact. Guardrails filter text. Custos decides — on every request, before the action — and leaves a tamper-evident record.",
    },
    {
      target: "pillars",
      title: "Four guarantees, each tested",
      body:
        "It decides rather than reports; it fuses three signals into one explainable verdict; its evidence can't be quietly edited; and overload never changes an answer.",
    },
    {
      target: "healing",
      title: "Governed self-healing",
      body:
        "When a data feed breaks, Custos diagnoses it, proposes a tested repair and applies it only when a named person approves. Live demo 2 shows it.",
    },
    {
      target: "proof",
      title: "Proof — including what went against us",
      body:
        "The detector is calibrated, the system is load-tested, and our pre-registered study on real loans showed drift alone is a poor gate. We publish that, and it shaped what we built next.",
    },
    {
      target: "integrate",
      title: "Integration",
      body:
        "A company adds Custos with a few lines in the service it already has. BLOCK and REVIEW arrive as exceptions the code must handle, so a held decision can never silently proceed.",
    },
    {
      target: "cta",
      title: "Where to go next",
      body:
        "Live demos to see it work, Documentation for every detail, Console for the operator's view of a real account.",
    },
  ],
  demo: [
    SWITCHER,
    {
      target: "hero",
      title: "Demo 1: the trust gate",
      body:
        "A loan bot approves loans automatically, and Custos sits between the bot and the money. You'll see it hold an unknown model, approve healthy traffic, notice the population change, block a rule breach, and catch someone editing the evidence.",
    },
    {
      target: "howto",
      title: "How to drive this screen",
      body: "Four steps, printed here so a first-time presenter never has to remember them.",
    },
    SYSCHECK,
    STEPPER,
    {
      target: "step-card",
      title: "The step card",
      body:
        "What will happen, the button that does it on the real system, and — once it has run — the result: Custos's verdict, the trust score on its real scale, and the reason in plain words.",
    },
    SAY,
    {
      target: "side",
      title: "Context on the side",
      body:
        "The applicant — the same person in every step, so any change in the answer comes from the world changing — what each verdict means, and what to do if something goes wrong.",
    },
  ],
  healing: [
    SWITCHER,
    {
      target: "hero",
      title: "Demo 2: governed self-healing",
      body:
        "Custos detects and diagnoses what went wrong, proposes a repair it can actually make, tests it on real decisions, and applies nothing until a named person approves.",
    },
    {
      target: "loop",
      title: "The seven stages",
      body:
        "Detect, diagnose, propose, shadow test, human approves, apply, verify. The approval stage is highlighted because it is the point: a person decides, and their name is recorded.",
    },
    {
      target: "playbook",
      title: "What it proposes — and what it refuses",
      body:
        "A broken feed gets a quarantine, never a re-baseline. A population shift gets a re-baseline or a retrain request. Custos never retrains a model it doesn't own.",
    },
    SYSCHECK,
    STEPPER,
    {
      target: "step-card",
      title: "The step card",
      body:
        "Before steps 2 and 4, type your name in “Approving as”: the approval is recorded on the audit chain under that name.",
    },
    {
      target: "queue",
      title: "The live approval queue",
      body:
        "The same queue an operator uses in the console: each incident's diagnosis, every proposed repair with its shadow test, and approve or reject buttons.",
    },
  ],
  agent: [
    SWITCHER,
    {
      target: "hero",
      title: "Demo 3: a different business",
      body:
        "An AI agent that issues customer refunds. Not one line of Custos changed — only configuration: the model, its inputs, two rules and the signal weights. This is the proof Custos isn't tied to lending.",
    },
    SYSCHECK,
    STEPPER,
    {
      target: "step-card",
      title: "The step card",
      body:
        "Each step runs the real gateway: an ordinary refund, a runaway loop, a manipulated refund, and a fraud ring — with the verdict, trust score and reason for each.",
    },
    SAY,
  ],
  docs: [
    {
      target: "docs-nav",
      title: "Everything, in one place",
      body: "Every section of the documentation. Click one to jump to it; the highlight follows as you scroll.",
    },
    {
      target: "#decision",
      title: "How a decision is made",
      body: "The request path from start to finish, and the eight-rule cascade that turns signals into a verdict — in order.",
    },
    {
      target: "#healing",
      title: "Governed self-healing",
      body: "How diagnosis works, the playbook, the shadow test and the approval rules — and what self-healing cannot do yet.",
    },
    {
      target: "#api",
      title: "API reference",
      body: "Every endpoint on the gateway and the control plane. Interactive versions run at localhost:8000/docs and :8001/docs.",
    },
    {
      target: "#validation",
      title: "Validation and results",
      body: "Calibration, load testing and the field study — the numbers behind every claim on this site.",
    },
    {
      target: "#limitations",
      title: "Limitations",
      body: "What Custos does not do yet, stated plainly. Reviewers ask; the answers are here.",
    },
  ],
  console: [
    {
      target: "console-gate",
      title: "Connect an account",
      body:
        "Paste the API key that ./app.sh printed (also in .run/api-key.txt). Easier: run any live demo — it connects the console to its own account automatically.",
    },
    {
      target: "console-head",
      title: "The operator console",
      body:
        "What a company sees day to day, for the connected account: its thresholds, which engines run, and fail-open or fail-closed. Turn on “Explanations” for a plain-English line on every panel.",
    },
    {
      target: '[data-tour="console-grid"] > :nth-child(1)',
      title: "Models",
      body: "Every registered model, whether it has a baseline, and a button to re-measure drift now. Re-measuring also runs self-healing detection.",
    },
    {
      target: '[data-tour="console-grid"] > :nth-child(2)',
      title: "Drift monitor",
      body: "The selected model's drift over time, and which inputs moved — the difference between the world changing and one data feed breaking.",
    },
    {
      target: '[data-tour="console-grid"] > :nth-child(3)',
      title: "Recent decisions",
      body: "Every verdict as it happens: ALLOW, REVIEW or BLOCK, with its trust score, reasons and latency.",
    },
    {
      target: '[data-tour="console-grid"] > :nth-child(4)',
      title: "Audit chain",
      body:
        "The tamper-evident record of every decision and every self-healing step. “Verify chain” proves nothing was edited — or names the record that was. “Export” downloads the evidence for an auditor.",
    },
    {
      target: "console-healing",
      title: "Incident queue",
      body: "Self-healing repairs waiting for a person: approve or reject, with your name recorded.",
    },
  ],
};
