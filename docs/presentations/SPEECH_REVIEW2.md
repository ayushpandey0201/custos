# Review-2 Speech — Custos

> **Deck:** `Custos_Phase2_Review2.pptx` — 24 slides, 17 October 2026.
> **Time:** about 14–16 minutes at a normal pace.
>
> **The story of Review-2 in one line:** *at Review-1 we told you where our
> system broke; this time we show you each of those breaks fixed, measured
> before and after — and two new defects we caught ourselves on the way.*
>
> Three rules while presenting:
> 1. **Never read the slide out.** The slide is for their eyes; you are for their ears.
> 2. **Say the bold sentence on every slide.** Everything else can flex.
> 3. **When a number improved, say what it was before.** Progress is only visible
>    as a comparison.

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
random review**. That is on slide 20, deliberately, and you should own it, not hide it.

---

## Slide 1 — Title

> Good morning. I'm Ayush Pandey, with Vivek Boora and Nitin, under the guidance
> of Dr. Seemanthini K G.
>
> This is Review-2 of **Custos** — a runtime trust layer for machine learning
> models.
>
> **At Review-1 we told you where our system broke. Today we'll show you each of
> those breaks fixed, measured before and after.**

---

## Slide 2 — Table of Contents

> I'll open with what we promised at Review-1 and what happened to each promise,
> then walk the system from motivation to design, show what's new, and close with
> results, the defects we found, and the plan to the final review.

*Ten seconds. Don't read the bullets.*

---

## Slide 3 — Abstract

### In simple words
A model is trained once and then trusted forever — but the world it learned from
keeps changing. When that happens the model doesn't crash; it stays up and keeps
answering confidently, and it's wrong. Custos sits in front of the model and, on
every request, decides whether this decision should go ahead.

### What to say
> Models are validated once and trusted indefinitely, but their data keeps
> changing. A drifted model fails quietly — up, confident, and wrong.
>
> Custos sits between a model and the action taken on its output. On every
> request it combines three signals — drift, business policy and per-request risk
> — into ALLOW, REVIEW or BLOCK within fifty milliseconds, and records every
> verdict in a tamper-evident log.
>
> **We validate the detector by calibration, the gateway by load testing — and
> our own tooling has found five defects in our own system, all fixed.**

---

## Slide 4 — Progress since Review-1 ⭐

> **This slide is the heart of a "progressive" review. Spend real time on it.**

### What's on the slide
Every commitment from the Review-1 closing slide, with a status: **Done / In
progress / Not started**, and the evidence.

### What to say
> At Review-1 our closing slide made commitments. Here's what happened to every
> one of them — including the ones we didn't do.
>
> **Done:** admission control, and moving the audit write off the hot path.
> Together these doubled the load we can handle within budget. I'll show the
> before-and-after on slide 15.
>
> **Done, and the answer was no:** the Lending Club validation. We ran a
> pre-registered study on 589,186 real loans — and our core assumption failed. I'll
> show you exactly how on slide 20.
>
> **Not started:** model versioning and the Postgres measurement. Both are on our
> work plan.
>
> **And one thing we didn't promise but did:** the risk engine. At Review-1 it was
> a placeholder. It's now a real, live signal.

### Why this works
Examiners trust a team that shows its *not-done* items. Two "not started" rows
make the five "done" rows believable.

---

## Slide 5 — Introduction: Overview and Motivation

### The figure
Top line: drift is only checked at quarterly reports (blue dots), with no signal
in between. Bottom line: the data actually shifts at some point (red dot). The red
box is the **blind window** — weeks where every automated decision is made by a
model nobody knows has drifted.

### What to say
> A model is validated once, deployed, and trusted indefinitely. Drift gets
> checked on a quarterly report — **but decisions are made every second.**
>
> Between two reports, the data shifts — and from that moment until somebody
> reads the next report, every decision is made by a model that's quietly wrong.
> A practitioner we interviewed put it simply: *you cannot wait three months.*

### Real example, if you want one
> Zillow in 2021: an algorithm automatically bought houses. The market moved
> under it, every individual offer still looked reasonable — and they wrote down
> over 300 million dollars in one quarter and shut the business. The model never
> crashed. That's the failure this project is about.

---

## Slide 6 — Existing System vs Proposed System

### In simple words
- **Monitoring tools** (Evidently, Arize, Fiddler) *watch from the side* and
  report afterwards. Like a CCTV camera.
- **Guardrails** (NeMo, Bedrock) *do* block in real time — but only on content:
  bad language, personal data, jailbreaks.
- **Custos** is the security guard at the gate: it stops the decision itself,
  based on whether the model still fits its traffic.

### What to say
> Monitoring tools sit beside the request path and report afterwards. Guardrails
> block in real time, but only on content.
>
> **Nothing we found gates the decision itself on whether the model still fits
> the traffic it's being given. That's what Custos does.**

⚠️ **Never say "nobody blocks in real time"** — guardrails do. Say *"drift is
treated as telemetry, never as a verdict."*

---

## Slide 7 — Objectives, Scope and SDGs

### What to say
> Five objectives. The first four are from Review-1: put drift on the live
> request path within fifty milliseconds, attribute it to the inputs that moved,
> fuse three signals into one explainable verdict, and record every verdict
> tamper-evidently.
>
> **The fifth is new, and the load test forced it on us: stay correct under
> overload — refuse requests we can't serve, never queue them, and never let load
> change our answers.**
>
> On scope: Custos doesn't train, serve or retrain models. It decides and records;
> humans act.

---

## Slide 8 — Literature Survey

### What changed since Review-1
Eight papers, every one checked against its real published venue. Two are new:

- **Paleyes, Urma & Lawrence — ACM Computing Surveys 2022.** Surveys real ML
  deployments; finds monitoring and trust are problems *in practice*, at every
  stage. Proposes no mechanism.
- **Rauba et al. — "Self-Healing Machine Learning", NeurIPS 2024.** An LLM watches
  a deployed model, diagnoses why it degraded, and **repairs the model by
  itself**.

### Why Rauba matters — this is your sharpest contrast
> Self-healing ML fixes the model *after* it degrades, autonomously, with no human
> checkpoint and no record of individual decisions. Custos does the opposite: it
> stops the **decision in flight**, sends it to a human, and records why. One
> repairs the model; the other protects each decision while the model is
> unreliable. They're complementary — but only one of them is accountable for
> the decision being made right now.

### What to say
> Eight works, each verified against its venue. **Every one either stops at
> detecting drift, or repairs the model afterwards. None gates the decision that's
> being made right now.**

---

## Slide 9 — Research Gap and Objectives

> Every gap the survey left maps to an objective: drift never reaches the live
> request — we put it there. Drift is one unexplained number — we attribute it per
> input. Policy and reliability are separate systems — we fuse them. Decision logs
> can be edited — ours are tamper-evident.

---

## Slide 10 — Requirement Analysis and Specification

### What's new
Three requirements added since Review-1:
- **FR11** — score per-request risk: unusual amount, request velocity.
- **FR12** — never auto-approve a model in the significant drift band.
- **NFR7** — overload is refused, never queued.

### What to say
> Review-1's requirements, plus three new ones. **NFR7 is the one the load test
> forced on us — overload must be refused, never queued.**

---

## Slide 11 — System Design: Architecture

### In simple words
Two planes. The **hot path** runs while a customer waits — it does the minimum.
The **cold path** (worker, control plane) does the slow statistics on a schedule.
The hot path just *reads* the answer the worker prepared.

> Think of a security guard with a list of banned vehicle numbers prepared
> overnight. The guard doesn't investigate anyone — he reads the list. That read
> is fast, which is the only reason the gate keeps moving.

### What to say
> Two planes — the request path does the minimum, statistics run offline.
> **New since Review-1: all three engines are live. Risk is no longer a
> placeholder.**

---

## Slide 12 — System Design: Decision Logic ⭐

### The cascade, left to right — the order IS the rule
1. Any veto → **BLOCK**
2. Trust below 0.30 → **BLOCK**
3. Model not registered → **REVIEW**
4. Every engine has no answer → **REVIEW**
5. **NEW — an input is quarantined (a person approved a hold) → REVIEW**
6. **NEW — drift in the significant band → REVIEW**
7. Trust below 0.60 → **REVIEW**
8. Otherwise → **ALLOW**

Rule 5 is the only rule a *person* switches on — it comes from self-healing
(slide 22). Say: *"Rule 5 is where a human's approved repair enters the cascade."*

### Why rule 6 exists — tell this story, it shows real engineering
> When we made the risk engine live, we checked the maths — and found we'd broken
> something.
>
> Before, risk was always excluded, so drift carried most of the weight, and a
> badly drifted model could *never* reach ALLOW. That was true — but only by
> accident of the weights.
>
> Adding a third live signal reduced drift's share. Suddenly a model with severe
> drift could be **approved**, if policy and risk both looked clean. That's the
> exact failure this whole system exists to prevent.
>
> **So we made it a rule instead of an accident: a significantly drifted model is
> never auto-approved, however reassuring the other signals are.** It's tested
> directly.
>
> *Then add:* And then we tested whether this rule actually helps on real loans.
> Hold that thought — slide 20 has the answer, and it isn't the one we wanted.

---

## Slide 13 — Implementation: Status

> Thirteen of fourteen components complete. The new ones are marked: the risk
> engine, admission control, the Lending Club study and governed self-healing.
> Versioning is for the final review.

---

## Slide 14 — Implementation: Risk Engine (new) ⭐

### What it is, simply
Drift asks *"does the model still fit?"* Policy asks *"is this action allowed?"*
Neither asks **"is this one request strange?"** — that's risk.

### The two checks

**1. Amount — is this loan amount unusual?**
> Custos remembers the last 2,000 amounts for each customer company and each
> model. A new amount is compared to the *typical* one.
>
> Example: if loans here are usually around ₹2 lakh, a ₹2.1 lakh loan is normal —
> no risk. A ₹9 lakh loan is far outside — maximum risk.

It uses the **median**, not the average. Why? Because one ₹5 crore fraud attempt
would drag an *average* upward and make the next fraud look normal. The median
ignores a handful of extreme values. (Tested: five ₹5 crore requests don't move
what "normal" means.)

**2. Velocity — is one customer firing requests in a burst?**
> Up to 3 requests a minute from one customer: fine. 10 or more: maximum risk.
> Bursts are a classic sign of fraud — or a runaway AI agent.

### Two design choices to defend
- **Worst, not average.** If the amount is extreme, a normal velocity must not
  hide it. One red flag is enough.
- **It refuses to guess.** Until it has seen 50 amounts it doesn't know what
  "normal" is, so it abstains. With no amount and no customer id, the whole engine
  says *"I don't know"* — and Custos leaves it out rather than treating silence
  as "safe". Same rule as everywhere else in the system.

### What to say
> **Drift asks whether the model still fits. Policy asks whether the action is
> allowed. Risk asks whether this one request is unusual — and abstains rather
> than guess when it can't tell.**

---

## Slide 15 — Implementation: Admission Control (new) ⭐

### What was wrong at Review-1, simply
> Imagine a shop with one billing counter. When too many customers come in, the
> queue grows forever — and everyone waits, including people who arrived first.
> Worse, staff start rushing and making mistakes.

That's what our gateway did: under overload it **queued** every request, served
*fewer* requests per second as load grew (congestion collapse), and — the
serious part — **its answers changed**. Checks timed out, were dropped, and about
13% of loans that should have been approved were sent to review.

### What we changed
1. **Moved the audit write off the main loop.** It was blocking everything; now a
   dedicated writer thread does it, one at a time (so the hash chain stays safe).
2. **Admission control.** Custos now holds at most **8** requests in progress.
   Past that, it immediately says *"503 — not now"*, instead of queueing. The
   caller's SDK then follows that company's own policy — fail-open or fail-closed
   — exactly as designed at Review-1.

### Why 8?
> Little's law: waiting time ≈ number queued × time each takes. At 16 we measured
> 69 ms at 200 req/s — over budget. At 8, 28 ms. It's a capacity setting — it
> changes how many requests wait, never what any verdict is.

### The chart — left panel, latency (grey = Review-1, blue = now)
- 100 req/s: **49 ms → 9 ms**
- 200 req/s: **94 ms ❌ → 28 ms ✅** — budget now holds at double the load

### Right panel, requests actually served
- At 400 req/s offered: **74 → 204** served per second
- At 800: **72 → 190**

### What to say
> **At Review-1, overload made the gateway queue, collapse, and change its
> answers. Now it refuses what it can't serve.**
>
> The budget now holds to two hundred requests a second — double Review-1. Under
> overload we serve nearly three times as many requests. **And the number we care
> most about: verdicts changed by load went from up to 985 per run to zero.**

### The honest part — say it before they ask
> At 400 and above the latency is still too high, because one Python process
> saturates around 300 requests a second, and the queue forms before our gate can
> see it. The fix is more worker processes — that's on the work plan.

---

## Slide 16 — Results: Live Demonstration

### The five acts
| Act | What happens | Verdict |
|---|---|---|
| 1 | A model nobody registered asks to disburse money | REVIEW — we don't guess |
| 2 | Registered, baseline captured, healthy traffic | ALLOW — trust 0.91 |
| 3 | Incomes fall, borrowing rises | drift 0.18 → 0.91 |
| 4 | Same application, same code | **REVIEW — trust 0.54** |
| 5 | Policy veto on a large disbursement | BLOCK, then tampering caught |

### Why the numbers differ from Review-1
> Two reasons. Risk is now live and says the loan amount is normal, which adds a
> little trust. And while building self-healing our tests caught that the drift
> window was counting the baseline's own rows as live traffic — healthy drift
> read 0.02 because the baseline was partly compared with itself; the honest
> figure is 0.18, still "stable". The verdict is still REVIEW — and now the reason is the drift floor, stated in
> plain words: *"model drift is in the significant band; a model this far from its
> baseline is not auto-approved regardless of other signals."*

### What to say
> **Same model, same code, nobody changed a setting — only the incoming
> population changed, and the answer changed with it.** And now the reason is
> spelled out, not just a number below a threshold.

---

## Slide 17 — Results: Drift Attribution

> One number tells you *something* moved. This tells you *what* moved:
> utilisation most (PSI 1.70), then income (1.22) — and credit score (0.04) didn't
> move, and isn't blamed.
>
> **If everything moved, the world changed. If one thing moved, your data feed
> probably broke. Those need opposite responses — this breakdown tells them
> apart.**

---

## Slide 18 — Validation: Calibration

### The idea, simply
Custos doesn't learn anything — it **measures**. You validate a measuring
instrument by giving it something whose answer you already know.

> You check a weighing scale with a known 1 kg weight — not by weighing random
> things and hoping.

So we shift the income data by an amount *we chose*, and check what Custos reads:
- **No shift → 0.030** — "stable". (Not exactly zero, and it shouldn't be: two
  samples are never identical.)
- **One standard deviation** (average income 60,000 → 45,000, a recession) **→
  1.019** — four times the industry's "significant" line.
- The line only goes up: more drift in, bigger number out.

### What to say
> **Custos is a measuring instrument, so we validate it like one: shifts of a
> known size in, readings checked against the known answer.**

---

## Slide 19 — Validation: Field Study — How It Was Run ⭐

### The idea, simply
Calibration proved the detector measures drift **correctly**. This study asks a
different question: **does gating on drift actually help?** If humans can only
review some loans, does Custos send them the *right* ones?

### How it was set up
- **Real data:** 2.26 million Lending Club loans. We kept 589,186 matured 36-month
  loans from 2012–2015 — loans whose outcome (repaid or defaulted) is known.
- **A model trained on 2007–2011**, never updated — the exact situation Custos is for.
- **Seven strategies** each pick **5%** of loans for a human to review. Score =
  how many of the picked loans really defaulted.
- **Pre-registered:** hypotheses and what each result would mean were committed
  and pushed to GitHub **before we downloaded the data**. We couldn't move the
  goalposts even if we wanted to.

### Two bugs we caught before the real run — tell these
> First: Lending Club writes dates like "Dec-2015". Our tool sorted them as text,
> so "Aug-2018" would have become the 2007 baseline. Scrambled results that look
> believable.
>
> Second: our first definition of "harm" was AUC. On test data we found AUC can't
> see the model's *level* going wrong — it predicted 17% defaults when reality was
> 30%, and AUC didn't move. We fixed the definition and recorded why — before
> seeing real data.

### What to say
> **Calibration proves the detector is correct. This study tests whether using it
> actually helps** — on real loans, with real outcomes, with the rules written down
> before we saw the data.

---

## Slide 20 — Field Result: Our Core Assumption Failed ⭐⭐

> **The most important slide. Slow down. Do not apologise — this is rigour.**

### Reading the chart, simply
Each bar: out of 1,000 loans a strategy sent to a human, **how many really
defaulted.** Higher is better. The dashed line is **random** — just picking loans
blindly: 140 per 1,000, because 14% of all loans defaulted.

| Strategy | Defaults caught per 1,000 reviews |
|---|---|
| Model's own risk score | **292** — about 2× random |
| Our proposed blend | 274 |
| Per-request novelty | 188 |
| Random | 140 |
| **Population drift — Custos today** | **126 — worse than random** |

### Why it happened — know these three points cold
1. **Drift pointed at the safest loans.** Drift peaked in 2012–13, when Lending
   Club *changed how it priced loans*. Those quarters had *fewer* defaults than
   average, so Custos sent reviewers to the wrong place.
2. **Drift was "significant" almost all the time** — 13 of 16 quarters. A warning
   that is always on can't tell you anything.
3. **The model did go wrong — drift just couldn't tell which way.** It
   *over*estimated risk for two years, then *under*estimated it. Drift was "high"
   in both.

**And the drift floor from slide 12** would have sent **92% of all loans** to
human review — and those loans defaulted at 14.2%, the same as random. Safe, but
useless.

### What to say
> We asked one question: if humans can review only 5% of loans, does gating on
> drift send them the right ones? We wrote down our hypotheses and pushed them to
> GitHub before downloading the data.
>
> **The answer was no. On 589,186 real loans, gating on population drift — how
> Custos works today — caught fewer bad loans than picking at random.** The
> model's own risk score caught about twice as many.
>
> We're not hiding this. It's the most valuable thing we learned this semester,
> because it tells us exactly what to build next: review queues ranked by risk,
> with drift as a monitoring signal — not as the gate.

### If they push: "So your project failed?"
> The *assumption* failed, and our method caught it — that's what the method is
> for. A system that had never been tested against real outcomes would still be
> claiming drift gating works. Ours now knows it doesn't, on this data, and why.
> The policy rules, risk engine, audit chain and admission control are all
> unaffected.

---

## Slide 21 — Engineering Rigour: Problems We Found in Our Own System ⭐

### The seven
| # | Found by | Problem | Status |
|---|---|---|---|
| 1 | Load test (R1) | Our 0.5 ms figure measured the wrong timer — real was 49 ms | Fixed: now 9 ms at the same load |
| 2 | Load test (R1) | Audit log dropped records and still said "all verified" | Fixed: 0 lost from 2 to 48 writers |
| 3 | Load test (R1) | Overload changed verdicts (~13% flipped) | Fixed: 0 flips |
| 4 | Unit test (R2) | Replay tool sorted dates as text | Fixed + regression test |
| 5 | Fusion maths (R2) | Live risk let a drifted model reach ALLOW | Fixed: explicit drift-floor rule |
| 6 | **Pre-registered study (R2)** | **Drift gating worse than random on real loans** | **Not yet fixed — gating to be rebuilt** |
| 7 | Self-healing tests (R2+) | Drift window scored the baseline's own rows as live traffic (healthy drift read 0.02; honestly 0.18) | Fixed + regression test |

### What to say
> **Seven problems, all found by our own tooling, none visible to a test that sends
> one request at a time.** Six are fixed. The study result is the largest — and
> it's the one that sets our plan for the final review.

---

## Slide 22 — Governed Self-Healing: Built ⭐⭐

### Why this slide matters
It answers two things at once. **Custos is not a lending bot**: the core has no
lending logic — a request is a model, an action, inputs and context — and
lending is our test case because it has public, real outcome data. And **the
self-healing MLOps we promised is built and running**, not a roadmap.

### The loop, top row — all seven stages are built
| Stage | What it does |
|---|---|
| Detect | Runs on every drift recompute |
| Diagnose | **Broken feed** (an input stuck on one value in ≥ 90% of recent requests, or missing in ≥ 50%) vs **population shift** |
| Propose | Broken feed → **quarantine** the input. Shift → **re-baseline** (undoable) or a **retrain request** to the owner |
| Shadow test | Replays up to 500 of the model's real recorded decisions through the real decision logic with the repair applied |
| Human approves | A **named** person. A repair that failed its shadow test cannot be approved |
| Apply | Effective on the next request |
| Verify + audit | Checked only on traffic that arrived *after* the repair; every step on the hash chain |

### The bottom row — one real run, numbers from the live system
1. The credit-score feed dies; **200 of 200 applications are still allowed** — the model keeps working on garbage.
2. Custos diagnoses it: credit score stuck at 720 in 100% of requests.
3. Shadow test: **351 of the last 401 decisions** would have been held. (Careful — that's *recent* decisions, healthy ones included, not "351 made on the dead feed".)
4. A named person approves; the next applicant is held, with the input and incident named in the reason.
5. The feed is fixed; Custos verifies it on fresh traffic and proposes a release — freeing 201 held decisions.
6. Released by a person: ALLOW again, and the audit chain verifies.

### What to say
> Custos is domain-agnostic MLOps infrastructure: it gates any model whose
> output triggers an action. Our field study told us drift is a poor per-decision
> gate but a strong alarm — so Custos now **acts on the alarm**.
>
> The hard part is diagnosis. A credit-score feed stuck at one value and a real
> recession both look like "drift" — but they need opposite repairs. So Custos
> tells them apart, proposes a repair it can actually make, tests it on real
> decisions, and applies it **only when a named person approves**.
>
> It also knows what *not* to do. It will never re-learn "normal" from a broken
> feed, and it never claims to retrain a model it doesn't own — that's a recorded
> request to the owner.
>
> Rauba et al. at NeurIPS 2024 heal models autonomously. We add the human
> checkpoint and the evidence.

### Show it live (about 3 minutes)
Dashboard → **Self-healing** → five buttons. Type your name before steps 2 and 4.

### If they push
- **"So it's autonomous?"** No — by design. It proposes and tests; a person approves.
- **"What can't it detect?"** A feed that's wrong but still varies — a unit change, an offset. That reads as a population shift; the reviewer sees the per-input evidence. It's in our limitations.
- **"How do you know who approved?"** The name is on the hash chain and can't be changed afterwards. It isn't authenticated yet — Custos has company keys, not user accounts. Per-user sign-in is on the work plan.
- **"Does it slow the hot path?"** One cached lookup per request: p99 at 200 req/s went from 28 to 31 ms, budget 50.

---

## Slide 23 — Work Plan to the Final Review

> First, rebuild the gating around what the data says works: review queues ranked
> by the model's own risk, with drift kept as a monitoring signal. Second,
> replicate the study on a second credit dataset — one dataset can't support a
> general claim. Then extending self-healing: more fault signatures — a unit
> change, a partial outage — and per-user sign-in for approvers. Then scaling out
> to multiple gateway workers, measuring on Postgres, and the final report.

---

## Slide 24 — Conclusion

> **397 tests passing. The latency budget holds to 200 requests a second, double
> Review-1. Overload no longer changes our verdicts. All three trust signals are
> live. And governed self-healing is built.**
>
> **And the hardest result: on 589,186 real loans, gating on drift did worse than
> random review. We pre-registered it, reported it as measured, and it now decides
> what we build next.**
>
> Thank you — we're happy to take questions.

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
> exactly what slide 22 shows: governed self-healing, built.

**"Isn't this just a lending bot?"**
> No. The lending bot is a small demo in `examples/`. The core has no lending
> logic — a request is a model, an action, inputs and context, so it gates fraud,
> claims, triage or an AI agent's payments the same way. We test on lending
> because that's where public, real outcome data exists.

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
- [ ] If presenting from Google Slides: upload it, then check slides 4, 8, 10, 13,
      21 and 23 — the tables. Google Slides resizes to 10×5.6 in, which squeezed the
      tables last time.
- [ ] **Contributions table (slide 24):** it shows Review-1 ownership. The new
      work — risk engine, admission control, the field study, self-healing — isn't assigned to
      anyone, because who did what is yours to state. Add it if you want credit
      attributed.
- [ ] `./app.sh` the morning of, so the demo is warm. The API key is in
      `.run/api-key.txt`.
- [ ] **For the live demo, open http://localhost:5173 → “Live demo”.** Check the
      light is green, then click through the seven steps. Every step tells you
      what to click, what to say and what to point at — no key to paste.
- [ ] **Run all three demos once** (Live demos → 1, 2, 3). In demo 2, type your
      name in “Approving as” before steps 2 and 4.
- [ ] Do one full practice run tonight. Use “Run the demo again” at the end to
      reset; each run starts from a clean slate.
