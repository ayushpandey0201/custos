# Review-2 Speech — Custos

> **Deck:** `Custos_Phase2_Review2.pptx` — 15 slides, 17 October 2026.
> **Time:** about 8–9 minutes of slides, then about 10 minutes of live demo.
>
> **The story in one line:** *Custos checks every model-driven action before it
> happens — and we can prove it works, including the result that went against us.*
>
> The slides are deliberately short. Detail lives on the dashboard's **Inside
> Custos** page — open it in a browser tab before you start, and go there when
> a question goes deeper than a slide. The 25-slide version
> (`Custos_Phase2_Review2_detailed.pptx`, notes in `SPEECH_REVIEW2_DETAILED.md`)
> is the backup for anything else.
>
> Three rules while presenting:
> 1. **Never read the slide out.** It's for their eyes; you are for their ears.
> 2. **Say the bold sentence on every slide.** Everything else can flex.
> 3. **Bring the reviewer in.** Three moments below are marked 🎯 — use them.

---

## The numbers to know by heart

Every one of these is measured, and the source is in the repo.

| What | Review-1 | Review-2 | Source |
|---|---|---|---|
| Tests passing | 274 | **397** | `pytest` |
| Load the 50 ms budget holds to | 100 req/s | **200 req/s** | `benchmarks/results-*.json` |
| p99 latency at 100 req/s | 49 ms | **9 ms** | same |
| p99 latency at 200 req/s | 94 ms ❌ | **28 ms** ✅ (31 ms with self-healing's check) | same |
| Verdicts flipped ALLOW→REVIEW under overload | up to **985 per run** | **0** | same |
| Requests served at 400 req/s offered | 74/s | **204/s** | same |
| Live trust signals | 2 of 3 (risk was a stub) | **3 of 3** | `engines/risk/engine.py` |
| Demo Act 4 trust | 0.48 | **0.54** — still REVIEW, now held by the drift floor | `run_demo` |
| Self-healing demo | not built | feed dies → **200 of 200 still allowed** → diagnosed → shadow test: **351 of 401** would be held → approved → fixed → released | dashboard → Self-healing |
| Lending Club study (589,186 real loans) | not run | **drift gating 126 vs random 140** per 1,000 reviews — worse than random | `experiments/gating/RESULTS_v1.md` |

**The honest limits, also by heart:** at 400 req/s and above the budget is still
missed (12–43 s p99), because one Python process saturates near 300 req/s; the
fix is more worker processes, which is on the work plan. And the big one: on real
loans, gating on population drift — the idea Custos was built on — did **worse than
random review**. That is on slide 13, deliberately, and you should own it, not hide it.

---

## Slide 1 — Title
> Good morning. We're presenting **Custos** — a runtime trust layer for
> production AI. Four words for what it does: **decide, explain, record, heal.**

## Slide 2 — Table of Contents
> We'll cover the problem, what exists, our design, what we built and measured —
> and then show it running live.

## Slide 3 — Abstract
> **Models are validated once and then trusted forever — and when the world
> changes, they fail quietly.** Custos sits between a model and the action it
> triggers, and answers ALLOW, REVIEW or BLOCK — in under 50 milliseconds, with a
> reason, on a record nobody can quietly edit. And when a data feed breaks, it
> proposes the repair — but a person approves it.

## Slide 4 — Overview and Motivation
🎯 *Ask the room:* "How often do you think a bank re-checks its credit model?"
*(Let them answer.)*
> Usually quarterly. But decisions happen every second. **Models don't crash —
> they go quietly wrong.** Zillow's pricing model kept buying houses as the
> market moved, and they wrote off $304 million in one quarter.

## Slide 5 — Existing vs Proposed
> Today's tools report after the fact — a dashboard shows drift last week.
> **Custos is on the decision path: it decides before the action happens.**

## Slide 6 — Objectives, Scope and SDGs
> Five objectives — the last two are new this review: staying correct under
> overload, and repairs only with human approval. **Scope: Custos gates any
> model-driven action; it never trains or retrains a model.**

## Slide 7 — Literature Survey
> Six verified papers, 2013 to 2024. **Every one detects or diagnoses — none acts
> on the decision while it's happening.** The closest, Rauba et al. at NeurIPS
> 2024, heals models autonomously — with no human and no record. That's our gap.

## Slide 8 — Research Gap → Objectives
> Each gap maps straight to one of our objectives — that's how the design was chosen.

## Slide 9 — Requirements
> On the left, what Custos must do. On the right, the guarantees it must keep —
> **the most important: if Custos fails, the caller must never fail.**

## Slide 10 — Architecture ⭐
> **Two planes.** The gateway answers every request: authenticate, admit, ask
> three engines at once, fuse, decide, record. Everything slow — the statistics,
> the repairs — runs offline and reaches the gateway as one cached number.
> *(Point at the "Inside Custos" tab if they want the full HLD and LLD.)*

## Slide 11 — Decision Logic
> Eight rules, in order — **rules are checked before the score.** A veto always
> wins; an unknown model is never auto-approved; a drifted or quarantined model
> never reaches ALLOW, however good its score looks.

## Slide 12 — Implementation
> Everything is built and tested — **397 automated tests; 31 milliseconds at 200
> requests a second; and overload no longer changes a single verdict** (it used
> to flip up to 985). Versioning is for the final review.

## Slide 13 — Results: the Field Study ⭐⭐
🎯 *Before showing the chart:* "We tested the core idea on 589,186 real loans,
with the method written down before we saw the data. Guess — did gating on drift
beat random review?" *(Let them guess.)*
> **It didn't — it caught fewer defaults than random.** The model's own risk score
> caught 2.1 times more. We report it as measured, and it changed our plan: the
> next gate ranks by risk, and drift becomes the alarm — which is what self-healing uses.

## Slide 14 — Self-Healing and Beyond Lending ⭐
> **When a data feed breaks, Custos diagnoses it, proposes a repair, tests it on
> real decisions — and a named person approves.** And the same engine works in
> any domain — we'll show an AI agent issuing refunds, with no code changed.

## Slide 15 — Conclusion and Work Plan
> **Custos gates any model-driven action — it decides, explains, records and
> heals.** Next: risk-ranked review, a second dataset, and scaling out. The team
> split is on the slide.
>
> *Pause, then read the big line — slowly:*
> **"Models decide. Custos makes sure they still deserve to."**
>
> *If you want to land it harder, add the quote beneath it:* "A model that is
> running is not a model that can be trusted. Custos checks the difference —
> every decision, every time."
>
> And now — the demo.

🎯 *During demo 2 (self-healing), step 2:* turn to the reviewer — "Ma'am / Sir,
would you like to approve this repair?" Let them type their name in "Approving
as" and press the button. In step 5, point at their name on the tamper-evident
record. **This is the moment they remember.**

---

# Likely questions — new for Review-2

**"Why 8 for the in-flight limit? Isn't that just tuned to pass?"**
> It's sized by Little's law and checked by measurement: wait ≈ queue length ×
> time per request. At 16 we measured 69 ms; at 8, 28 ms. It changes how many
> requests wait, never what any verdict is — that's the difference between a
> capacity setting and tuning a detector.

**"If you refuse requests, isn't that worse than a slow answer?"**
> A slow answer under overload was arriving *seconds* late, after the caller had
> usually given up — and 13% of them were the wrong answer. A fast refusal lets
> the caller's own policy decide immediately: fail-open companies proceed, loudly
> flagged; fail-closed companies stop. That's the contract we designed at Review-1.

**"Why does a shed request become an ALLOW for fail-open tenants? Isn't that unsafe?"**
> It's the tenant's choice, per tenant. Fail-open exists because a safety layer
> that takes production down gets removed within a week. And a fail-open ALLOW is
> flagged `failed_open=True` — it's never mistaken for a real approval.

**"Why median, not mean, in the risk engine?"**
> So outliers can't hide outliers. One huge fraud attempt drags a mean upward and
> makes the next one look normal. The median ignores a handful of extreme values.

**"Why is the risk 'worst component' and not an average?"**
> One red flag is enough. Averaging would let a normal velocity dilute an extreme
> amount.

**"Your risk engine has fixed thresholds — z of 3 and 10, 3 and 10 per minute. Arbitrary?"**
> They're conservative starting defaults and they're constants in one file. The
> same rule as drift applies: we won't tune them on the data we evaluate them on.
> Per-tenant overrides are the obvious next step.

**"Doesn't risk lower your Act 4 margin — 0.54 is close to 0.60?"**
> Yes, and that's exactly why we added the drift floor. Act 4's REVIEW no longer
> depends on 0.54 being below 0.60 — it's held by an explicit rule that a
> significantly drifted model is never auto-approved.

**"Is the risk engine's memory shared between servers?"**
> No — it's per process today. With several workers each sees part of the traffic,
> which makes the signal a little less sensitive, never wrong. A shared Redis
> history is the multi-server step.

**"Couldn't you have tuned the study until drift looked good?"**
> No — that's what pre-registration prevents. The hypotheses, metrics and the
> meaning of each outcome were committed and pushed to GitHub at 21:44; the data
> was downloaded at 21:54; the results were pushed at 22:01. Anyone can check the
> timestamps.

**"Why did drift point at safe loans?"**
> Most of the measured drift was Lending Club repricing its loans — `int_rate` is
> set by the platform, not the borrower. The quarters with the most repricing had
> fewer defaults. Drift measures *change*, and change is not the same as danger.

**"Is drift useless, then?"**
> Not proven — this is one dataset, and the biggest drift was a platform policy
> change. What it shows is that drift against a fixed old baseline is a poor guide
> to *which decisions* need review. We're keeping drift as a monitoring signal and
> testing a rolling baseline and a second dataset next.

**"Why not just use the risk score, then — what does Custos add?"**
> The risk ranking needs somewhere to run: a gate on the decision path, policy
> rules with vetoes, velocity checks, an audit trail that can prove what happened,
> and fail-safe behaviour under overload. That's the part of Custos the study
> didn't touch — and the part we're building the next phase around.

**"Self-healing ML exists — why not just fix the model automatically?"**
> Rauba et al. at NeurIPS 2024 do exactly that, and it's complementary. But a
> repair happens *after* degradation, and it acts on the model. While the model is
> unreliable, decisions are still being made — Custos is what protects those, and
> it leaves the decision to fix the model with a human, with evidence. That's
> exactly what slide 14 shows: governed self-healing, built.

**"Isn't this just a lending bot?"**
> No. The lending bot is a small demo in `examples/`. The core has no lending
> logic — a request is a model, an action, inputs and context. Live demo 3 runs
> an AI refund agent with no code change, and slide 14 and the Inside Custos page show where else it
> applies. We test on lending because that's where public, real outcome data exists.

**"Lending, fraud and insurance are crowded — and so is model monitoring. How would this ever survive in the market?"**
> We agree those are crowded — as *models* and as *dashboards*. Custos is
> neither. It doesn't score fraud and it doesn't just chart drift; our own study
> shows drift alone is a weak signal. It's the layer that decides at the moment
> an automated action happens, puts a person in the loop, and keeps evidence a
> regulator would accept. Two things make that space open: regulation — the EU
> AI Act requires human oversight and record-keeping for high-risk uses like
> credit, hiring and triage — and AI agents, which are being given tools that
> move money with very little between "decided" and "done". Our buyer isn't the
> fraud team; it's whoever owns risk for *every* automated decision.
>
> *If pushed on risks:* larger platforms could add a guardrail feature. Our
> defence is owning the approval workflow and the evidence — once a company's
> decision history lives in Custos, it's hard to move — and validating the
> first market with risk and compliance teams before building further.

**"Is this MLOps?"**
> Yes — the runtime half of it: monitoring, governance and control of models in
> production — and now governed repair: it diagnoses broken feeds and population
> shifts and applies tested repairs once a person approves. Retraining stays with
> the model's owner; Custos records the request with the evidence.

**"Is the 400+ req/s latency a failure?"**
> It's a known limit of one process, and we say so on the slide. The improvement
> is that overload is now *safe*: it no longer changes answers and no longer
> collapses throughput. Getting it *fast* at that load needs more workers — on the
> work plan.

---

# Live demo — running order (about ten minutes)

Open **http://localhost:5173 → Live demos**. The three demos are linked: each ends
with a "Next demo" button. Press **Guide me** (bottom right) on any page if you
want the screen explained element by element.

| # | Demo | What it proves | The line to land |
|---|---|---|---|
| 1 | **The trust gate** (lending, 7 steps) | Custos stops trusting a drifted model, blocks a rule breach, and catches an edited audit log | "Same applicant, same code — a different answer, because the world changed." |
| 2 | **Self-healing** (lending, 5 steps) | A dead data feed is diagnosed, quarantined with a person's approval, verified and released | "Custos proposes and tests the fix. A person decides — and their name is on the record." |
| 3 | **AI agent guardrail** (e-commerce, 5 steps) | A second domain with **zero code changes**: a refund agent loops, is talked into a bad refund, meets a fraud ring | "We didn't change one line of Custos for this — only configuration." |

**Demo 3 — what you'll see** (numbers from a real run):
- **Loop:** the same customer refunded 12 times in seconds → trust falls 0.97 → 0.17: six ALLOW, two REVIEW, four BLOCK. Nobody wrote a rule for loops; the risk engine saw the burst.
- **Talked into it:** ₹19,000 refund on a ₹9,500 order → BLOCK, by the rule "an agent may never refund more than the order was worth". *"You can talk an AI agent into almost anything. You can't talk your way past a rule — rules are parsed, not prompted."*
- **Fraud ring:** 300 requests from days-old accounts; drift is checked every 50. The alarm fires at the first check — **about 40 got through before it, about 260 were held**. Say the lag out loud; it's honest and it's why drift is an alarm, not a gate.
- Self-healing opens an incident and proposes re-baselining. **Say: "A reviewer should reject this — the shift is fraud, not a new normal. That's exactly why a person approves."**

**Why the weights differ** (if asked): the refund agent weighs risk 0.8, drift 0.1,
policy 0.1; lending uses drift 0.5, policy 0.3, risk 0.2. An agent acting on its own
at machine speed is judged mostly on what it's doing right now. Weights are
per-company configuration.

**Finish in the Console:** *"Everything you just saw happened for real — here it is
as an operator sees it: every decision, the audit chain, and the incident waiting
for a person."*

---

# Before you present — checklist

- [ ] Open `Custos_Phase2_Review2.pptx` and flip through once. I checked layout
      by calculation, not by rendering (no LibreOffice on this machine).
- [ ] If presenting from Google Slides: upload it, then check slides 7, 9, 12 and
      15 — the tables. Google Slides resizes to 10×5.6 in, which squeezed the
      tables last time.
- [ ] **Contributions table (slide 15):** it shows Review-1 ownership. The new
      work — risk engine, admission control, the field study, self-healing — isn't assigned to
      anyone, because who did what is yours to state. Add it if you want credit
      attributed.
- [ ] Open **Inside Custos** (http://localhost:5173/#/design) in a second browser
      tab before you start — it's where deep questions go.
- [ ] `./app.sh` the morning of, so the demo is warm. The API key is in
      `.run/api-key.txt`.
- [ ] **For the live demo, open http://localhost:5173 → “Live demo”.** Check the
      light is green, then click through the seven steps. Every step tells you
      what to click, what to say and what to point at — no key to paste.
- [ ] **Run all three demos once** (Live demos → 1, 2, 3). In demo 2, type your
      name in “Approving as” before steps 2 and 4.
- [ ] Do one full practice run tonight. Use “Run the demo again” at the end to
      reset; each run starts from a clean slate.
