# Custos — Detailed Slide-by-Slide Explanation

> **This file is for understanding, not for reading aloud.**
> `SPEECH.md` is the short script you speak from. This one explains *what every
> slide actually means*, in the simplest English possible, with examples — so
> that when someone asks a question, you know the answer rather than the line.
>
> Read this once slowly the night before. Read `SPEECH.md` on the day.
>
> The deck has 22 slides: a title slide plus 21 content slides.

---

## First, the whole project in five sentences

1. A machine learning model is trained on data from the past.
2. It goes live, and the world keeps changing — but the model does not.
3. So the model slowly becomes wrong, while still looking perfectly healthy.
4. Custos sits in front of the model, measures how far the world has moved, and
   **stops the model from making decisions when it has drifted too far.**
5. Every decision it makes is written into a log that cannot be edited without
   the edit being detectable.

If you can say those five sentences, you can defend the project.

---

## Words you must be able to define

Learn these before anything else. Half the questions you get will be someone
checking whether you understand your own vocabulary.

| Word | Simplest meaning | Example |
|---|---|---|
| **Model** | A program that learned a pattern from past data and uses it to make predictions | A program that looks at a loan application and predicts "will this person repay?" |
| **Drift** | The live data no longer looks like the data the model learned from | Model trained when average income was 60,000; now applicants average 45,000 |
| **Baseline** | A frozen snapshot of what the data looked like when the model was built | A photograph you keep and compare everything against |
| **Feature** | One input column | income, credit utilisation, credit score, months employed |
| **PSI** | One number for *how different* today's data is from the baseline | 0.02 = same, 0.83 = very different |
| **KS** | A second, different way of measuring the same difference | A second opinion |
| **Severity** | All the per-feature drift numbers combined into one score from 0 to 1 | 0.83 means "badly drifted" |
| **Trust score** | All three checks combined into one number from 0 to 1 | 0.99 = trust it, 0.48 = don't |
| **Verdict** | The final answer: ALLOW, REVIEW, or BLOCK | REVIEW = send to a human |
| **Engine** | One independent check | We have three: policy, drift, risk |
| **Veto** | One check overruling everything else | Policy says "never above 5 lakh" → BLOCK regardless of score |
| **Degraded** | A check that has no confident answer right now | We leave it out of the average rather than let it guess |
| **Fail-open** | If Custos itself breaks, requests are allowed through | A safety system that stops the business gets switched off within a week |
| **Hot path** | Code that runs while a customer is waiting | Must be fast — 50 ms budget |
| **Cold path** | Setup and admin work; nobody is waiting | Can be slow and thorough |
| **p99 latency** | 99 out of 100 requests finish faster than this | Fairer than an average, which hides the bad ones |
| **Hash chain** | Each record is mathematically locked to the one before it | Edit any old record and every record after it breaks |
| **Tamper-evident** | We cannot stop someone editing the database, but we can always prove they did | Like a seal on a medicine bottle |
| **Multi-tenant** | One installation serving several separate customers who cannot see each other | Like flats in one building with separate locks |

---

# SLIDE 1 — Title

### What is on screen
College name, department, project title **CUSTOS — Runtime Drift Enforcement for
Production ML Models**, your three names with USNs, and Dr. Shruthi K R as guide.

### What to say
> Good morning. I'm Ayush Pandey, with Vivek Boora and Nitin, guided by
> Dr. Shruthi K R.
>
> Our project is called **Custos**. It's Latin for *guard*.
>
> **We built a system that sits in front of a machine learning model and stops
> it from making decisions when it is no longer safe to trust.**

Then stop. Let it land for two seconds.

### If they ask "why the name?"
Custos is Latin for guard or guardian. It guards the moment where a model's
output turns into a real action.

---

# SLIDE 2 — Table of Contents

### What to say
> I'll cover the problem and why existing tools don't solve it, the literature
> and the gap we found, our design, what we built, a live demonstration, how we
> validated it, and what happened when we deliberately tried to break it.

Ten seconds. Do not read the bullets out.

---

# SLIDE 3 — The Problem

### What is on screen
A timeline figure, and the line: *"A model is validated once, deployed, and then
trusted indefinitely. Drift is checked on a quarterly report — but decisions are
made every second."*

### What it means in simple English
Before a model goes live, it is tested carefully. Somebody checks its accuracy,
signs it off, and it is deployed.

After that, almost nobody checks it again — maybe once a quarter in a report.

But the model is making decisions **every second**. So between two quarterly
reports there can be *millions* of decisions made by a model nobody has verified
recently.

### The key insight
The model does not break loudly. It does not crash. It does not throw an error.
It keeps answering, with exactly the same confidence it had on day one — while
being quietly wrong.

**A crash is easy to detect. Quiet wrongness is not.** That is the whole problem.

### Example to use
> Think of a doctor who trained thirty years ago and never read anything since.
> They are confident. They are experienced. They answer immediately. And they
> are slowly becoming dangerous — but nothing about how they behave tells you
> that.

### What to say
> A model is validated once, before it goes live. Then it's deployed, and it's
> trusted indefinitely.
>
> But the world it learned from keeps moving. Incomes fall. Spending patterns
> change. The model doesn't know that. It keeps answering with the same
> confidence it had on day one.
>
> Drift gets checked on a quarterly report. **But decisions get made every
> second.**
>
> So there's a window — sometimes weeks long — where a model is quietly wrong
> and still approving loans. Nobody finds out until the defaults appear months
> later. And every decision in that window was made at full confidence.

---

# SLIDE 4 — Why Existing Tooling Does Not Close It

### What is on screen
A before/after figure and the line: *"The tools exist. They sit beside the
request path and report afterwards. None of them can stop the decision that is
about to be made."*

### What it means in simple English
Monitoring tools already exist — Evidently, Arize, Fiddler, SageMaker Model
Monitor. They are good tools. They *do* detect drift.

But they are **observers, not guards**. They watch from the side, calculate
drift over a batch of traffic, and raise an alert. A human reads the alert
later — minutes or hours later — and decides what to do.

Meanwhile, the model keeps making decisions the entire time.

### The real-world example — use this, it is powerful

> In 2021 Zillow, a large American property company, ran a business called
> Zillow Offers. An algorithm looked at a house, predicted what it would sell
> for, and **automatically made an offer to buy it.** Real money, thousands of
> times over.
>
> The model was working exactly as built. But the housing market it had learned
> from was moving away underneath it.
>
> Every individual offer still looked reasonable. Nobody could point at one and
> say "that's the broken one." The damage was spread across thousands of
> decisions, each slightly too high.
>
> By November 2021 they shut the whole business down. **A 304 million dollar
> write-down in one quarter, up to 569 million in total, and 2,000 people — a
> quarter of the company — lost their jobs.**
>
> Zillow's own words: they were "unintentionally purchasing homes at higher
> prices than our current estimates of future selling prices."
>
> **The model never crashed. It never threw an error. It was up, healthy and
> answering every request — and that is exactly the failure nobody had a tool
> for.**

### The timeline that makes the point

| Time | What happens |
|---|---|
| Hour 0 | Market shifts. Model starts overpaying. |
| Hours 0–6 | Offers keep going out at full speed. Drift is calculated over a window; the window has not closed yet. |
| Hour 6 | Batch job finishes. Drift detected. Alert fires. |
| Hour 8 | A human opens the dashboard and reads it. |
| Hour 10 | Team investigates, agrees, pauses the model. |

Every existing tool would have caught this — **eventually**. The information
existed. It just was not in the room where the decision was being made.

### About guardrails — be accurate here
There *are* tools that block in real time: NeMo Guardrails, AWS Bedrock
Guardrails, Aporia. They genuinely stop actions on the request path.

But they block on **content** — bad language, personal data, jailbreak attempts.

**None of them gate the decision on whether the model still fits the traffic it
is being given.** Drift is treated as telemetry — it goes to a dashboard, never
becomes a verdict. That is the specific, narrow gap we fill.

> ⚠️ **Do not say "nobody blocks in real time."** That is false and an examiner
> may know it. Say: *"drift is universally treated as telemetry, never as a
> verdict."* That is true and defensible.

---

# SLIDE 5 — Literature Survey

### What is on screen
A six-row table: paper, venue, year, what it contributes, its limitation, and
the gap it leaves.

### What it means
Six papers across three areas:

**Area 1 — ML systems infrastructure**
- *Hidden Technical Debt in ML Systems* (Google, NeurIPS 2015). Famous paper.
  Its point: in a real ML system, **the machine learning is a tiny box in the
  middle**; everything around it — data plumbing, configuration, monitoring — is
  where the problems live. It names the gap but builds nothing.

**Area 2 — Drift detection**
- *A Survey on Concept Drift Adaptation* (ACM Computing Surveys 2014) — the
  standard textbook of drift detection methods. All offline.
- *Learning under Concept Drift* (IEEE TKDE 2019) — consolidates the field.
  Assumes you eventually learn whether you were right (labels arrive). In
  lending you do not, for months.
- *Failing Loudly* (CMU, NeurIPS 2019) — carefully compares detectors. Offline
  batch study, no time limit considered.

**Area 3 — Tamper-evident logging**
- *Certificate Transparency* (Google, IETF RFC 6962, 2013). How the internet
  proves a security certificate log has not been secretly edited. We borrowed
  this idea for ML decisions.

### The sentence that matters
> **Every one of these works stops at detection. Not one of them puts the
> measurement in front of the decision.**

### What to say
> Six papers, three areas.
>
> Google's *Hidden Technical Debt* names the infrastructure gap but doesn't
> close it. The drift surveys give us the theory, but both treat detection as
> something you do offline. *Failing Loudly* compares detectors carefully —
> again offline, with no time limit.
>
> **Point at the last row.** The last one is different. Certificate Transparency
> is how the internet proves a certificate log hasn't been edited. We applied
> that idea to machine learning decisions — as far as our survey found, that
> hasn't been done before.
>
> **Every one of these works stops at detection. Not one puts the measurement in
> front of the decision.**

---

# SLIDE 6 — Research Gap and Objectives

### What is on screen
A figure mapping four gaps on the left to four objectives on the right.

### The four gaps and what we did

| Gap we found | What we built |
|---|---|
| Drift never reaches the live request | We put it there, inside a 50 ms budget |
| Drift is one number with no explanation | We report it per feature, so you know *which* input moved |
| Policy rules and reliability are separate systems | We fuse them into one score |
| Decision logs can be edited | We made ours tamper-evident with a hash chain |

### What to say
> Four gaps came out of that survey, and each became an objective.
>
> Drift never reaches the live request — so we put it there, inside a strict
> time budget. Drift is reported as one number with no explanation — so we
> report it per input. Policy and reliability are separate systems — so we fuse
> them. Decision logs can be edited — so we made ours tamper-evident.
>
> **Every gap on the left has a matching objective on the right, and every one
> is built and running today.**

---

# SLIDE 7 — Scope and SDG Alignment

### What it means
This slide is about **honesty**: saying clearly what we do *not* do. Examiners
respect a tight scope far more than an inflated one.

**In scope:** drift detection with per-feature attribution, policy evaluation,
signal fusion, runtime enforcement, tamper-evident audit, multi-tenant config.

**Out of scope — and say this confidently:**
- We do not train models
- We do not serve or host models
- We do not explain individual predictions
- We do not retrain or roll back — **we decide and record; humans act**

### The SDGs, simply
- **SDG 9 (Industry, Innovation, Infrastructure)** — we build auditable
  infrastructure for automated decisions.
- **SDG 10 (Reduced Inequalities)** — a drifted credit model can systematically
  reject a whole group of people unfairly. Blocking it limits that harm.
- **SDG 16 (Peace, Justice, Strong Institutions)** — verifiable records are what
  a regulator needs to audit an automated decision.

### If they ask "why don't you auto-fix the model?"
> Because retraining on the wrong data makes it worse, and because deciding to
> retrain is a judgement with cost and risk attached. We give the human the
> evidence and the moment to act. Auto-remediation is explicitly out of scope.

---

# SLIDE 8 — Requirements

### What is on screen
A table: ten functional requirements (what it must do) and six non-functional
ones (how well it must do it), plus the technology stack.

### The two that shaped everything
- **NFR1 — Gateway p99 ≤ 50 ms, 20 ms cap per engine.** This is why drift is
  computed offline. If we calculated statistics during the request, we could
  never hit 50 ms.
- **NFR2 — A Custos failure must not fail the caller.** This is *fail-open*. If
  our system dies, loans still process. A safety layer that takes down the
  business gets removed within a week.

### Simple explanation of functional vs non-functional
- **Functional** = *what* it does. "Register models." "Return ALLOW/REVIEW/BLOCK."
- **Non-functional** = *how well*. "Within 50 ms." "Without ever taking the
  caller down."

### What to say
> Ten functional requirements, six non-functional. Two of the non-functional
> ones drove the entire architecture: a fifty millisecond budget, and the rule
> that if Custos fails, the caller must still work.

---

# SLIDE 9 — System Architecture

### What is on screen
The architecture figure — two planes.

### The single most important idea in the project
**Split the work into two paths:**

- **Data plane (hot path)** — runs while the customer waits. Does the absolute
  minimum. 50 ms budget.
- **Control plane and worker (cold path)** — registration, configuration,
  statistics, dashboards. Nobody is waiting, so it can be slow and careful.

### The analogy to use
> Think of a security guard at a gate with a printed list of banned vehicle
> numbers. The guard does not investigate anyone — that would take hours. Some-
> body else prepares the list overnight. The guard just **reads** the list. That
> read is fast, which is the only reason the gate keeps moving.
>
> Our drift engine is that guard. The overnight work is the statistics.

### What to say
> Two planes. The data plane does the minimum possible work per request —
> everything expensive lives in the control plane or the offline worker.
>
> This split is not a detail. It is the reason a fifty millisecond budget is
> achievable at all.

---

# SLIDE 10 — Request Flow

### What is on screen
A sequence figure of one `/v1/evaluate` call, numbered steps.

### What happens, in order
1. Request arrives with an API key
2. Key → which customer (cached)
3. Load that customer's settings (cached)
4. Is this model registered? (cached)
5. Ask all three engines **at the same time** (not one after another)
6. Each engine has 20 ms; if it overruns it is cancelled and marked degraded
7. Combine the answers into one trust score — pure maths, no database
8. Apply the decision rules → ALLOW / REVIEW / BLOCK
9. Write to the audit chain
10. Save the feature values **after** the caller already has its answer

### Why "at the same time" matters
If you asked three engines one after another, the total time is the **sum**. If
you ask all three at once, the total is the **slowest one**. That means adding a
fourth check later costs nothing extra.

### What to say
> One call. Steps two, three and five are cached reads. Step seven is pure
> computation. Only eight and ten touch the database — and ten runs *after* the
> caller already has its answer.
>
> The engines are asked concurrently, so total time is the slowest engine, not
> the sum of all three. That's what makes adding a fourth signal free.

---

# SLIDE 11 — Drift Pipeline

### What is on screen
A figure showing the offline/online split.

### What it means in simple English
This slide answers: *"If statistics are slow, how are you fast?"*

**Offline (the worker, on a schedule):**
- Collect the feature values that recently came through
- Compare them against the frozen baseline
- Calculate PSI and KS for every feature
- Roll it up into one severity number
- Save it

**Online (during the request):**
- Read that saved number from a cache
- Subtract it from 1
- Done

### The crucial point
**No statistics run during a request.** The expensive work is paid for on a
schedule, not per customer. This is written up as ADR 0002 in our repository.

### Why the baseline never moves — explain this, it is subtle
You might think: compare today with yesterday. That fails badly.

> If the data moves 1% every day, then every day looks almost identical to the
> day before. Every comparison says "fine." But after six months you are 180%
> away from where you started and nobody ever raised a flag.
>
> It is the boiling frog problem. So we always compare to the **original**
> baseline, which never moves.

---

# SLIDE 12 — Decision Logic

### What is on screen
The decision cascade figure.

### How the final answer is produced
1. Each engine returns a score between 0 and 1
2. Engines with no confident answer (degraded) are **left out** of the average
3. The rest are combined as a weighted average — drift counts most (0.5), policy
   0.3, risk 0.2
4. If any engine issues a **veto**, the score is forced to 0
5. Then the cascade runs **in order**:
   - Veto → BLOCK
   - Model not registered → REVIEW
   - All engines degraded → REVIEW
   - Score below 0.30 → BLOCK
   - Score below 0.60 → REVIEW
   - Otherwise → ALLOW

### The most important design decision on this slide
**A degraded engine is excluded, never treated as 1.0.**

> If the drift engine has no data, we do not assume everything is fine. We
> remove it from the calculation and record that we did. An engine with no
> answer does not get a vote.
>
> If *every* engine is degraded, the answer is REVIEW — never ALLOW. You cannot
> earn an approval from a system that knows nothing.

### Why three verdicts and not two
> In lending, full automation is too risky and full manual review is too
> expensive. The middle answer is what makes the system usable in practice. The
> practitioner we interviewed said exactly that — you need a human eye somewhere.

---

# SLIDE 13 — Implementation Status

### What is on screen
An eleven-row table of components and their status.

### What to say
> Nine of eleven components are complete and exercised end to end. The remaining
> two are deliberate, not unfinished.
>
> The risk engine is registered and wired, but returns "degraded" on purpose —
> an unbuilt engine must not contribute trust it has not earned. The sidecar
> proxy, for callers not written in Python, is Review-2 work.

### If they ask "why is the risk engine empty?"
This is a strength, not a weakness — say it confidently:
> The seam exists and is wired in. Adding contextual risk later is a new file,
> not a refactor. And returning *degraded* rather than a confident 1.0 is
> deliberate: it is excluded from the calculation and the audit record shows
> exactly why. That is the honest behaviour for a check that does not exist yet.

---

# SLIDE 14 — Results: Live Demonstration

### What is on screen
The demo trajectory figure — trust score across five acts.

### What the demo shows
A lending bot auto-approves loans. Custos sits in front of it. One command, no
Docker, no external services.

| Act | What happens | Verdict |
|---|---|---|
| 1 | An unregistered model asks to disburse money | **REVIEW** — we don't guess about a model we've never seen |
| 2 | Register it, capture a baseline, healthy traffic | **ALLOW** — trust 0.99 |
| 3 | The population shifts — incomes fall, borrowing rises | severity 0.02 → **0.83** |
| 4 | **The same application, the same code, no config change** | **REVIEW** — trust 0.48 |
| 5 | A policy rule vetoes a large disbursement | **BLOCK**, then the audit chain catches tampering |

### The sentence that wins this slide
> **Same model. Same code. Nobody changed a setting. Only the incoming
> population changed — and the answer changed with it. That is the entire point
> of the project, demonstrated in one run.**

---

# SLIDE 15 — Results: Drift Attribution

### What is on screen
A bar chart of PSI per feature after the population shift.

### What it means
One severity number tells you *something* is wrong. It does not tell you what to
do about it.

So we break the number down by input:

| Feature | PSI | Band |
|---|---|---|
| utilisation | 0.500 | significant |
| income | 0.350 | significant |
| months_employed | 0.162 | moderate |
| bureau_score | 0.010 | **stable** |

### Why the last row is the important one
`bureau_score` did **not** move — and we do **not** blame it.

A drift system that blames every feature whenever anything changes is useless.
Pointing at the specific inputs that moved is what makes it actionable.

### The distinction that makes this valuable
> **If everything moved at once, the world changed — that's a real economic
> shift and you may need to retrain.**
>
> **If exactly one input moved and the others didn't, your data feed probably
> broke — and retraining would be completely the wrong response.**
>
> Those two situations need opposite reactions, and this breakdown is what tells
> them apart.

---

# SLIDE 16 — Data and Validation ⭐

> **This is the slide you said you don't understand. Read this section twice.**

### What is on screen
The thermometer paragraph, and a two-row table: **Calibration** and **Field**.

### Start from the question they will ask
Every project that touches ML gets asked: **"Where is your dataset?"**

For most projects the answer is easy: "We used this dataset, we trained on 80%,
tested on 20%, and got this accuracy."

**We cannot answer that way, and the reason is important.**

### The key realisation

**Custos does not learn anything from data.**

There is no training. No weights. No fitted parameters. Nothing inside Custos
was learned from examples.

Custos is a **measuring instrument**. You give it two sets of numbers and it
tells you how far apart they are, using two published formulas (PSI and KS).

### So what does "validation" even mean?

This is the crux. There are two different kinds of thing, validated two
different ways:

**A model** is validated on a dataset.
The question is *"does it predict correctly on data it has not seen?"*
Only real held-out data can answer that.

**An instrument** is validated by **calibration**.
The question is *"does it measure correctly?"*
And that requires inputs whose true value you **already know**.

### The example that makes it click

> You buy a weighing scale. How do you check it works?
>
> ❌ You do **not** put random objects on it and hope. If it reads 3.2 kg for a
> bag of rice, how would you know whether 3.2 is right?
>
> ✅ You put a **known 1 kg weight** on it. If it says 1 kg, it works. If it says
> 1.4 kg, it's broken.
>
> **The reference weight has to be known, or the reading isn't being checked
> against anything.**

Same with a thermometer: melting ice must read 0 °C, boiling water 100 °C. You
don't validate a thermometer by pointing it at random objects.

### Now apply it to Custos

Custos measures "how much has the data changed?"

To check that it measures correctly, we give it data where **we already know how
much it changed** — because we changed it ourselves, by an exact amount.

If we ran it on real loan data and it reported 0.34, **nobody on earth could
tell you whether 0.34 is the right answer**, because nobody knows the true
amount of drift in that data. There is no answer key.

> **This is why controlled data is not a shortcut. It is the only thing that can
> establish the detector is correct at all.**

### The two-row table, explained

| | What data | Question it answers | Do we know the right answer? | Status |
|---|---|---|---|---|
| **Calibration** | Data we generated, moved by an exact amount we chose | *Is the detector correct?* | **Yes** — we chose the shift | ✅ Done, 43 tests |
| **Field** | Real public credit data, replayed in time order | *Does it fire on drift that really happened?* | **No** — but nobody chose the drift | 🔧 Tool built, run is Review-2 |

**Neither is enough on its own.**

- Calibration alone: proves the tool is accurate, but maybe it never fires in
  the real world.
- Field alone: proves it fires, but you can never check whether the number is
  *correct*.

**Together, they are the standard way any measuring instrument is validated.**

### What to say

> Every ML project gets asked "where is your dataset?" Our answer needs one
> sentence of setup, because it isn't the usual answer.
>
> **Custos has no trained model in it. No weights, nothing learned from data. It
> is a measuring instrument.**
>
> That changes what validation means. You validate a model on a dataset, because
> the question is "does it predict well on data it hasn't seen." You validate an
> *instrument* by calibration, because the question is "does it measure
> correctly" — and for that you need inputs whose true value you already know.
>
> Nobody validates a weighing scale by putting random objects on it. You put a
> known one-kilogram weight on it. **The reference has to be known, or the
> reading isn't being checked against anything.**
>
> So we do both. Controlled data to prove the instrument is correct. Real data
> to prove it fires on drift nobody chose. The table shows what each is for —
> and the honest status of each.

---

# SLIDE 17 — Calibration: the Instrument in Ice and Steam ⭐

> **This is the proof for everything slide 16 claimed. Take your time here.**

### What is on screen
A line chart. X-axis: how much we moved the data. Y-axis: what PSI the detector
reported. Coloured bands in the background.

### Two words you must understand first

**Standard deviation (written σ, said "sigma")**
> A measure of how spread out numbers are.
>
> In our demo, income averages **60,000**, and most applicants fall within about
> **15,000** either side of that. So one standard deviation = 15,000.

**"Shifting by 1σ"**
> Means moving the average by one full standard deviation.
>
> In our case: **the average income drops from 60,000 to 45,000.** That is a
> recession-sized change — big, realistic, and exactly the kind of thing that
> should set off alarms.

### What the experiment actually does

For each amount of change — 0, 0.25σ, 0.5σ, 0.75σ, 1σ, 1.5σ, 2σ:

1. Generate 600 "original" applicants
2. Generate 600 "new" applicants, with the average income moved by that exact
   amount
3. Ask the detector: how different are these two groups?
4. Repeat 15 times so it isn't a fluke
5. Plot what it reported

**Because we chose the shift, we know what the answer should look like.**

### How to read the chart

The coloured bands are the **industry standard** thresholds — not invented by us.
Banks already use these:

| PSI | Band | Meaning |
|---|---|---|
| under 0.10 | 🟢 stable | basically the same data |
| 0.10 – 0.25 | 🟡 moderate | noticeably different, keep watching |
| above 0.25 | 🔴 significant | seriously different, investigate |

### The two numbers that matter most

**At 0σ — we changed nothing — it reads 0.030 (green, "stable").** ✅ Correct.

> And notice it does **not** read exactly zero — and it shouldn't. Two random
> samples from the same population are never perfectly identical. An instrument
> that reported a perfect zero would be lying to you.

**At 1σ — a realistic recession-sized shift — it reads 1.019.** ✅ Correct.

> That is **four times** the 0.25 "significant" threshold. It doesn't just detect
> the change, it screams about it.

### The third thing the chart proves: monotonicity

The line **only ever goes up**.

> More drift in → a bigger number out. Every single step. It can never go
> backwards.
>
> That property is called **monotonicity**, and it is what makes the score
> trustworthy. If more drift could sometimes produce a *smaller* number, you
> could never rely on the reading. We test this over 500 random perturbations.

### What to say

> This is the ice and the boiling water.
>
> We take one input — income — and shift its average by an amount we choose,
> measured in standard deviations. In our data one standard deviation is fifteen
> thousand, so a one-sigma shift means average income falling from sixty
> thousand to forty-five thousand. A recession.
>
> **Point at the left dot.** Zero shift — we changed nothing. It reads 0.030,
> inside the stable band. And notice it doesn't read exactly zero, and it
> shouldn't: two samples from the same population are never identical. An
> instrument reporting a perfect zero would be lying.
>
> **Point at the 1σ dot.** A realistic recession-sized shift reads 1.019 — four
> times the threshold credit teams already use for "this is serious."
>
> **And the line only ever goes up. Every step, more drift in means a bigger
> number out. That property is what makes the score trustworthy, and we test it
> over five hundred random perturbations.**
>
> The bands behind the line are not ours. They're the industry's. The point of
> this chart is that our numbers land where a bank already expects them to land.

---

# SLIDE 18 — What the Controlled Data Proves ⭐

### What is on screen
A five-row table. Left: what we check. Middle: how. **Right: why real data
couldn't check it.**

### The five checks, in simple English

**1. The arithmetic is right**
We computed a PSI value **by hand from the formula** and checked the code
produces the same number. For KS we built a case where the answer is exactly 0.5
by construction.
*Why not on real data:* there is no hand-computable right answer for 2.2 million
rows.

**2. Identical data reads "stable"**
Two samples from the same population report PSI 0.030 — below the 0.10 line.
*Why not on real data:* no real dataset is known to contain exactly zero drift.

**3. A known shift reads "significant"**
A 1σ shift reports 1.019 — four times the 0.25 threshold.
*Why not on real data:* the true shift is unknown, so the reading cannot be
graded right or wrong.

**4. The score never moves the wrong way**
500 random perturbations: increasing any feature's drift can **never** lower the
reported severity.
*Why not on real data:* you must control the input to know which direction is
correct.

**5. It refuses to guess**
An empty window raises an error rather than returning 0.0. Below 30 samples it
reports "insufficient data."
*Why this matters:* reporting **"no drift"** when you mean **"no data"** is
exactly the failure this whole system exists to prevent. Those two things look
identical if you're careless, and they are opposites.

### The right-hand column is the entire argument
> **Not one of these five could be checked on a real dataset — because on real
> data, nobody knows the true answer to compare against.**

### Then be honest about real data
> Real data answers a different question: does it fire on drift that occurs
> naturally? Our replay tool is built and works on any time-ordered CSV. Running
> it on the 2.2-million-row Lending Club dataset is our next step, and we say so
> on the final slide.

### If they ask "isn't generating your own data circular?"
> It would be if we were claiming predictive accuracy. We're claiming
> *measurement* accuracy — and for that, chosen inputs are **stronger** evidence,
> because the true answer exists and can be checked.
>
> The circular version would be tuning the detector until it produced a pleasing
> number on real data. That is the thing we specifically avoid.

### If they ask "why not MNIST or a standard benchmark?"
> Those are shuffled and have no time axis. **Drift is a property of *ordered*
> data** — with no time dimension there is no drift to detect. That's exactly why
> Lending Club is the right target: a real time axis and a documented regime
> change in 2008 and again in 2016.

---

# SLIDE 19 — Validating the Latency Claim

### What is on screen
A bar chart: request rate vs p99 latency, with a dashed line at 50 ms.

### What it means
On slide 8 we put a number in a document: 50 ms. **A number in a design document
is a promise, not evidence.** So we built the tool that could prove us wrong.

### One detail that makes the chart trustworthy — say this

> The obvious way to write a load tester is: send a request, wait for the reply,
> send another. That is **wrong**, and it's wrong in a flattering direction.
>
> When the server slows down, that design automatically sends *less* traffic —
> so the slow period is under-sampled and your p99 comes out far better than the
> truth. It's a known trap called **coordinated omission**.
>
> Ours decides every request's send time **before the run starts**, and measures
> from when it was *due*, not when we got round to sending it. So the chart
> cannot flatter us.

### How to read it
- 🟢 green = inside budget, 🔴 red = outside
- Dashed line = the 50 ms budget
- The "served" row underneath = how many requests per second actually completed

### The results
| Offered | p99 | Verdict |
|---|---|---|
| 50/s | 11 ms | ✅ |
| 100/s | 49 ms | ✅ |
| 200/s | 94 ms | ❌ |
| 400/s | 66 s | ❌ |
| 800/s | 150 s | ❌ |

### The honest conclusion
> **We hold the budget to 100 requests per second per instance.** Throughput
> keeps up to 200 — look at the "served" row — but the latency budget doesn't.
>
> And past that it doesn't plateau, it **collapses**. At 800 offered we serve 72.
> More load, less work done. That's a system that doesn't recover from a spike on
> its own, which is why admission control is on our next list.

---

# SLIDE 20 — What Load Testing Exposed

### What is on screen
A three-row table: what we believed / what we measured / what we did.

### This slide is you correcting yourself in public. That is its power.

**Finding 1 — our own published number was measuring the wrong thing**
> At the last review we said the gateway responds in half a millisecond. That
> number was real, but it measured our internal timer — and that timer **stops
> before we write the audit record**, which is the most expensive part.
>
> The number a caller actually experiences at the ceiling is **49 milliseconds**.
> Still inside budget — but 98% of the budget, not 1%. We'd rather tell you than
> have you find it.

**Finding 2 — the audit chain was dropping records** (detail on slide 21)

**Finding 3 — under overload it gives different answers**
> This is the one we found most interesting. Under overload the system doesn't
> just get slow — **it starts answering differently.**
>
> When engines exceed their 20 ms timeout they're dropped from the calculation by
> design, the score is computed from fewer signals, and about **13% of verdicts
> flip from ALLOW to REVIEW** — on traffic an idle gateway would have approved.
>
> Same model, same code, same config. Only the arrival rate changed.
>
> That's our safety design working correctly. But it means a traffic spike
> quietly turns automatic approvals into a human review queue, and an operations
> team needs to know that in advance rather than discover it.

---

# SLIDE 21 — Case Study: The Audit Log That Lied

### What is on screen
Symptom → Diagnosis → Fix.

### This is your best engineering slide. Slow down and tell it as a story.

**The symptom**
> Our strongest claim is tamper-evident evidence for **every** decision. Under
> concurrent writes we were losing entries — 2 out of 96.
>
> And here's the part that actually worried us: **the verification endpoint still
> reported the chain intact.** It said "all 94 entries verified."
>
> A hash chain detects a record that was **changed**. It cannot detect a record
> that was **never written**, because the remaining links are still consistent
> with each other. Our own audit tool was giving a green light on an incomplete
> log.

**The diagnosis — this is the part that shows engineering maturity**
> The tempting fix was a lock inside the application. We measured first, and
> it's a good thing we did.
>
> With one server process: **zero losses.** The event loop was already forcing
> those writes into a queue. The losses only appeared with **four** processes.
>
> Which means an in-application lock would have protected the one configuration
> that was **never broken**, and done nothing for the one that was — because
> those four processes can't see each other's locks.

**The fix**
> So the lock had to go where all four processes meet: the database. A per-tenant
> advisory lock, taken before we read the end of the chain. Plus randomised
> backoff on retries, because the original code retried instantly, which kept all
> the racers in lockstep colliding with each other.
>
> **Result: zero losses from two writers up to forty-eight. And throughput
> doubled, because the retry storm we removed was itself a large part of the
> load.**

**The lesson to leave them with**
> The obvious fix was the wrong fix, and only measuring where the bug actually
> lived told us that.

---

# SLIDE 22 — Contributions and Conclusion

### What is on screen
The headline numbers, the Review-2 plan, and the team contribution table.

> ⚠️ **This slide currently shows outdated numbers — see the note at the end of
> this file. Fix before presenting.**

### The correct closing numbers
- **274 tests passing**
- **50 ms p99 budget verified under load to 100 req/s per instance**
- **Two concurrency defects found by our own harness and fixed**
- **Audit chain demonstrated under an actual tampering attempt**

### The line that closes it
> **We'd rather show you a system we've stress-tested and found faults in than a
> system nobody has pushed hard enough to break.**

### The Review-2 plan
1. **Admission control** — shed load at the door instead of letting a spike
   silently fill a review queue
2. **Lending Club replay** — real drift across the 2008 crisis and 2016 policy
   change
3. **Model and data versioning + retraining trigger** — what practitioners named
   as prerequisites
4. **Move the audit write off the hot path**, then re-measure against PostgreSQL

### Then
> Thank you. I'm happy to take questions.

---

# The ten questions most likely to come

**"Where is your dataset?"** → Slides 16–18. Instrument, not model. Calibration
with known inputs; real data is the next step.

**"Isn't generating your own data circular?"** → Only if claiming predictive
accuracy. We claim measurement accuracy, where chosen inputs are stronger
evidence.

**"Where is the AI/ML in this?"** → It's infrastructure *for* ML, a recognised
subfield — our first cited paper exists to make that point. The statistics (PSI,
KS) are implemented from scratch and calibrated; slide 17 is the evidence.

**"Is this just monitoring?"** → Monitoring reports. We decide. Monitoring runs
after the fact; we run before the action and can stop it.

**"What if Custos itself goes down?"** → Requests are allowed through, recorded
loudly as a fallback rather than a judgement. A safety layer that takes down
production gets removed within a week.

**"Is half a millisecond realistic?"** → No, and we corrected it ourselves.
49 ms at our ceiling. Slide 20.

**"Your load test is on SQLite and one core — meaningless?"** → It's a floor, not
a ceiling. The harness takes a `--database-url`; PostgreSQL is Review-2. What we
defend today is the method and the three defects it found.

**"Why three verdicts?"** → Full automation is too risky, full manual review too
expensive. The middle answer is what makes it usable.

**"Why don't you retrain automatically?"** → Retraining on the wrong data makes
it worse, and you cannot retrain a broken data feed — you fix it. That's why we
tell you *which input* moved.

**"Why should we trust your numbers?"** → Because we published the ones that
embarrassed us. Slide 20 is us correcting a claim from our own last review.

---

# ⚠️ Before you present — slide 22 needs fixing

The deck you edited (`Custos_phase2_review1_ppt.pptx`) has an **older slide 22**
than the generated one. It currently says:

- ❌ "268 tests" → should be **274 tests**
- ❌ "measured gateway p99 of 0.5 ms" → this is the claim you are *correcting* on
  slide 20. Leaving it on slide 22 contradicts your own case study.
- ❌ Future work says "Load-test the gateway under concurrency" → **you already
  did this.** Slides 19–21 are that work.
- ❌ The contributions table says "268-test suite" in Nitin's row

Also: the tables on **slides 16 and 22 overflow the bottom of the slide** by
about 0.9 and 1.1 inches, because they are 3.28 in wide on a 10 in canvas.
Widening them to roughly 8.4 in fixes both.
