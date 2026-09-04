# Review-1 Speech

> Written to be **spoken**, in plain English. Roughly 9–11 minutes at a normal
> pace. Slide numbers match `Custos_Phase2_Review1.pptx`.
>
> Two rules while presenting: **say the sentence in bold on every slide**, and
> **never read the slide out**. The slide is for their eyes; you are for their
> ears.

---

## Slide 1 — Title

> Good morning. I'm Ayush Pandey, with Vivek Boora and Nitin, guided by
> Dr. Shruthi K R.
>
> Our project is called **Custos**. It's Latin for *guard*.
>
> **We built a system that sits in front of a machine learning model and stops
> it from making decisions when it is no longer safe to trust.**

*Pause. Move on.*

---

## Slide 2 — Contents

> I'll cover the problem, what already exists and why it isn't enough, our
> design, what we've built, and a live demonstration.

*Ten seconds. Don't linger.*

---

## Slide 3 — The Problem  *(timeline figure)*

This is your most important slide. Slow down.

> Here's how machine learning works in a bank today.
>
> A model is built and tested carefully. Then it goes live, and it starts making
> decisions on its own — approving loans, rejecting loans — thousands a day.
>
> Now, that model was built for a certain kind of customer. But the world moves.
> There's a recession, or a new product brings in different people. The customers
> applying today are not the customers the model was built for.
>
> The model doesn't know that. It keeps answering, just as confidently, and it
> keeps being wrong.
>
> **So how do we catch this? Point at the top line.** Today, teams check for this
> with a report. That report comes once a quarter.
>
> **Point at the red bar.** This is the gap. If the customers change in week two,
> nobody finds out until week twelve. And every single decision in between was
> made by a model that had already stopped working.
>
> **This isn't our theory. We interviewed two practitioners who run this in
> production, and one told us directly: "you need leading indicators — you cannot
> wait three months."**

---

## Slide 4 — Why Existing Tooling Does Not Close It  *(before/after figure)*

> Our first question was: surely someone has solved this?
>
> There are good tools — Evidently, WhyLabs, MLflow. **Point to the top row.**
> They do detect this problem. But look at where they sit. They watch from the
> side and they draw you a chart afterwards.
>
> A chart cannot stop anything. By the time you read it, the money is gone.
>
> **Point to the bottom row.** So we moved the check into the path itself.
> Every request has to pass through Custos before the action happens, and Custos
> gives one of three answers: allow it, send it to a human, or block it.
>
> **The tools that detect this problem cannot stop it. The systems that can stop
> things don't know about this problem. That gap is our project.**

---

## Slide 5 — Literature Survey

> We surveyed six papers across three areas.
>
> Google's *Hidden Technical Debt* paper at NeurIPS names the infrastructure gap
> but doesn't close it. The concept drift survey in ACM Computing Surveys and the
> IEEE review give us the theory, but both treat detection as something you do
> offline. *Failing Loudly* from Carnegie Mellon compares detectors carefully —
> again, offline, with no time limit.
>
> **Point at the last row.** The last one is different. Certificate Transparency
> is how the internet proves that a security certificate log hasn't been edited.
> Nobody had applied that idea to machine learning decisions. We did.
>
> **Every one of these works stops at detection. Not one of them puts the
> measurement in front of the decision.**

---

## Slide 6 — Research Gap and Objectives  *(mapping figure)*

> Four gaps came out of that survey, and each one became an objective.
>
> Drift never reaches the live request — so we put it there, inside a strict
> time budget. Drift is reported as one number with no explanation — so we
> report it per input. Policy and reliability are separate systems — so we
> combine them. And decision logs can be edited — so we made ours tamper-evident.
>
> **Every gap on the left has a matching objective on the right, and every one of
> those is built and running today.**

---

## Slide 7 — Scope and SDG Alignment

> Briefly, what we are and are not.
>
> We do not train models. We do not host models. We do not retrain them or roll
> them back. **Custos watches and decides. Humans act.**
>
> On sustainable development goals: this is infrastructure for accountable
> automation, it limits unfair automated credit decisions, and it produces
> records a regulator can verify.

---

## Slide 8 — Requirements

> Ten functional requirements, six non-functional.
>
> Two shaped everything else. **First**, the whole check must finish in under 50
> milliseconds, because it happens on every live request. **Second**, if our
> system ever fails, the customer's system must keep working — we are never
> allowed to become the reason something breaks.

---

## Slide 9 — System Architecture  *(figure)*

> The design splits in two, and this split is the key idea.
>
> **Point to the top.** The fast side handles live requests and does as little as
> possible — just reads an answer that's already been worked out.
>
> **Point to the worker box.** The slow side does the heavy mathematics on a
> schedule, in the background.
>
> **All the expensive work happens before the request arrives, so the live path
> only has to look up the answer.**

---

## Slide 10 — Request Flow  *(sequence figure)*

> This is a single request, step by step.
>
> The agent asks. We check who's asking. We check the model is known. **Point to
> step 4.** Then we ask all three checks at the same time, not one after another,
> so the total time is the slowest one, not the sum.
>
> We combine them, decide, write the record, and answer.
>
> **Point to step 10.** And this last step — storing the data for later analysis
> — happens *after* the caller already has their answer. They never wait for it.

---

## Slide 11 — Drift Pipeline  *(figure)*

> This is how we made it fast enough.
>
> **Point at the red line.** Nothing below this line runs while a request is
> waiting. Below it, on a schedule, we compare recent data against the original
> reference and work out how far it has moved. Above it, the live request just
> reads that number.
>
> **We do heavy statistics on full data windows, but a live request never waits
> for any of it.**

---

## Slide 12 — Decision Logic  *(cascade figure)*

> How three separate signals become one answer.
>
> We take a weighted average. Drift counts most, because it's the signal nothing
> else in the stack provides. If a check has no confident answer, we leave it out
> entirely rather than guessing — **a system that guesses in your favour when it
> doesn't know is worse than useless.**
>
> Then we walk this chain left to right. Any hard rule violation blocks
> immediately. Very low trust blocks. An unknown model goes to a human. And
> **point to the right end** — the only way to reach "allow" is to pass every
> single check.

---

## Slide 13 — Implementation Status

> Nine of eleven components are complete and working end to end.
>
> The two that aren't are deliberate. The risk engine is a slot we built and
> wired but left empty — and importantly, it reports itself as "no opinion" so it
> can't accidentally make things look safer than they are. The sidecar is
> Review-2 work.
>
> **This isn't a prototype. It's 268 passing tests and a system that runs with
> one command.**

---

## Slide 14 — Results: Live Demonstration  *(trajectory figure)*

This is where you win or lose. Be confident.

> Here's a loan approval bot running behind Custos. Watch the trust score.
>
> **Act 1** — a model we've never seen. We don't guess, we send it to a human.
>
> **Act 2** — properly registered, normal customers. Trust 0.99. Approved.
>
> **Act 3** — now the customers change. Incomes fall, borrowing rises. Our drift
> measure jumps from 0.02 to 0.83.
>
> **Act 4 — and this is the whole project in one moment.** Same loan application.
> Same model. Same code. Nobody changed a setting. And the answer is now different
> — held for a human, trust 0.48.
>
> **The verdict changed because the world changed.**
>
> **Act 5** — a policy violation. Blocked outright. Then we edited a record in the
> database to make a "blocked" look like "approved" — and the system caught it and
> told us exactly which record.

---

## Slide 15 — Results: Drift Attribution  *(figure)*

> One number tells you something is wrong. It doesn't tell you what to do.
>
> So we break it down by input. Borrowing rate moved most, income second.
>
> **Point at the bottom bar.** And this one — credit score — didn't move, and we
> don't blame it.
>
> **That matters more than it looks. If everything moved, the world changed. If
> one thing moved, your data feed probably broke. Those need opposite responses,
> and this breakdown is what tells them apart.**

---

## Slide 16 — Contributions and Conclusion

> Our contributions are split across architecture and the drift engine, the
> services and audit trail, and the SDK, dashboard and testing.
>
> To close: 268 tests passing. The check runs in half a millisecond against a
> 50 millisecond budget. And the audit trail caught real tampering in front of you.
>
> For Review-2: validate against the Lending Club dataset — two million real
> loans with real economic drift in them; add model versioning; load-test under
> pressure; and begin shadow-mode trials with partner startups.
>
> **Thank you. I'm happy to take questions.**

---

# Difficult terms, in plain English

Learn these. If you can define them simply, you look like you built it.

| Term | Say it like this |
|---|---|
| **Model drift** | The model still works the way it was built, but the world it was built for has changed. |
| **Data / covariate drift** | The information going *into* the model has changed shape. This is what we measure. |
| **Concept drift** | The relationship itself changed — the same customer is now riskier than before. We do **not** measure this; it needs outcomes we won't know for months. |
| **PSI** (Population Stability Index) | A single number for how far today's data has moved from the original data. Banks already use it. Under 0.10 fine, over 0.25 serious. |
| **KS statistic** (Kolmogorov–Smirnov) | A second opinion on the same question, measured a different way. We use both so a change can't hide from one of them. |
| **Baseline** | A saved snapshot of what the data looked like originally. Everything is compared against this, and it never moves. |
| **Severity** | All the per-input drift numbers combined into one score between 0 and 1. |
| **Trust score** | All three checks combined into one number between 0 and 1. Above 0.6 allow, below 0.3 block. |
| **Signal / engine** | One independent check. We have three: rules, drift, and risk. |
| **Veto** | One check saying "absolutely not" and overruling everything else. Only the rules engine can do this. |
| **Degraded** | A check that has no confident answer. We leave it out of the average rather than let it vote. |
| **Fail-open** | If our system breaks, requests are allowed through rather than blocked. A safety layer that takes down the business gets switched off. |
| **Hot path / data plane** | The code that runs while a customer is waiting. Must be fast. |
| **Control plane** | The setup and admin side. Nobody is waiting on it, so it can be slow and thorough. |
| **p99 latency** | 99 out of 100 requests finish faster than this. A fairer measure than an average. |
| **Hash chain** | Each record is mathematically locked to the one before it, so editing any old record breaks every record after it. |
| **Tamper-evident** | We can't stop someone editing the database — but we can always prove they did. |
| **SHA-256** | The standard mathematical fingerprint used to build that lock. |
| **Multi-tenant** | Several separate customers on one installation, unable to see each other's data. |
| **Shadow mode** | We give a verdict, the company logs it but doesn't act on it. Zero risk — how you'd trial this safely. |
| **SDK** | The small piece of code a company adds to use us. Ours is five lines. |
| **Fan-out** | Asking all three checks at the same time instead of one after another. |
| **ADR** (Architecture Decision Record) | A short written note recording why we made a decision, so it can be questioned later. |

---

# Likely questions

**"Where is your dataset?"** — See `docs/DATASET.md`, and section 2 especially.
> We validate two ways, because we're testing a *measuring instrument*, not a
> model. To prove a thermometer works you put it in ice and boiling water, where
> you already know the answer — you don't point it at random objects. So we test
> the detector against shifts of a known size, which is the only way to prove the
> measurement is *correct*. Then, separately, we replay real credit data through
> it to show it fires on drift nobody chose. We've built that replay tool and it
> works on any time-ordered CSV; running it on the two-million-row Lending Club
> set is our next step.

**"Why not just retrain the model more often?"**
> Retraining is expensive and you need to know *when*. That's the question we
> answer. And you cannot retrain a broken data feed — you have to fix it, which
> is why we tell you which input moved.

**"Isn't this just monitoring?"**
> Monitoring reports. We decide. Monitoring runs after the fact; we run before
> the action, and we can stop it.

**"What if Custos itself goes down?"**
> Requests are allowed through and it's recorded loudly as a fallback, not a
> judgement. A safety layer that takes production down gets removed within a week.

**"Is half a millisecond realistic?"**
> That's honestly measured, but on one machine with a local database. Load
> testing under real concurrency is explicitly Review-2 work — we're not
> claiming production numbers yet.

**"Why three verdicts instead of two?"**
> Because in lending, full automation is too risky and full manual review is too
> expensive. The middle answer is what makes it usable — and the practitioner we
> interviewed said exactly that: "you need some human eye to validate everything."
