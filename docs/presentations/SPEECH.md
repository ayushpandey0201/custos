# Review-1 Speech

> Written to be **spoken**, in plain English. Roughly 14–16 minutes at a normal
> pace across 22 slides. Slide numbers match `Custos_Phase2_Review1.pptx`.
>
> **If you are short on time, cut slides 7 and 18 and compress 10-12 into one
> pass.** Do not cut 16-17 or 21: the calibration argument and the audit-chain
> case study are the two places this stops sounding like a student project.
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

## Slide 16 — Data and Validation

> Every project in this room gets asked "where is your dataset?" Our answer needs
> one sentence of setup, because it isn't the usual answer.
>
> **Custos has no trained model in it. No weights, no fitted parameters, nothing
> learned from data. It is a measuring instrument.**
>
> That changes what validation means. You validate a model on a dataset, because
> the question is "does it predict well on data it hasn't seen." You validate an
> *instrument* by calibration, because the question is "does it measure
> correctly" — and for that you need inputs whose true value you already know.
>
> Nobody validates a thermometer by pointing it at random objects and hoping. You
> put it in melting ice and check it reads zero, then boiling water and check it
> reads a hundred. **The reference points have to be known, or the reading isn't
> being checked against anything.**
>
> So we do both. Controlled data to prove the instrument is correct. Real data to
> prove it fires on drift nobody chose. The table shows what each one is for — and
> the honest status of each.

---

## Slide 17 — Calibration: the Instrument in Ice and Steam  *(figure)*

> This is the ice and the boiling water.
>
> We take one input — income — and shift its average by an amount we choose,
> measured in standard deviations. Then we ask the detector what it sees. Because
> we picked the shift, we know what the right answer should look like.
>
> **Point at the left-hand point.** Zero shift — we changed nothing. It reads
> 0.030, inside the "stable" band. Notice it does not read exactly zero, and it
> shouldn't: two samples from the same population are never identical. An
> instrument that reported a perfect zero would be lying.
>
> **Point at the one-sigma point.** A one-standard-deviation shift reads 1.019 —
> four times the 0.25 threshold that credit-risk teams already use for "this is
> serious."
>
> **And the line only ever goes up. Every step, more drift in means a bigger
> number out. That property — monotonicity — is what makes the score
> trustworthy, and we test it over five hundred random perturbations.**
>
> The bands behind the line are not ours. They are the industry's. The point of
> this chart is that our numbers land where a bank already expects them to land.

---

## Slide 18 — What the Controlled Data Proves

> Five specific properties, backed by forty-three tests on the detectors alone.
>
> We check the arithmetic against a PSI value computed by hand from the
> definition. We check that identical data reads stable. We check that a known
> shift reads significant. We check the score can never move the wrong way. And
> we check that it refuses to answer when it doesn't have enough data — an empty
> window raises an error rather than returning zero, because reporting "no drift"
> when you mean "no data" is exactly the failure this system exists to prevent.
>
> **Now look at the right-hand column, because that's the real argument. Not one
> of these could be checked on a real dataset — because on real data, nobody
> knows the true answer to check against.**
>
> If you ran PSI on two million real loans and got 0.34, there is no way to know
> whether 0.34 is right. That's not a shortcut we took. It's the reason
> controlled data is the only thing that can establish correctness at all.
>
> Real data answers the other question — does it fire in the wild — and our
> replay harness is built and works on any time-ordered CSV. Running it on
> Lending Club is our next step, and we say so on the last slide.

---

## Slide 19 — Validating the Latency Claim  *(figure)*

> Earlier we put a number on a slide: fifty milliseconds. A number in a design
> document is a promise, not evidence. So we built the thing that could prove us
> wrong.
>
> One detail matters, and it's the reason this chart is trustworthy. The obvious
> way to write a load tester is to have workers send a request, wait, send
> another. That's wrong, and it's wrong in a flattering direction: when the
> server slows down, that design automatically sends less traffic, so the slow
> period gets under-sampled and your p99 comes out far better than the truth.
> It's a known trap called coordinated omission. **Ours schedules every request
> before the run starts and measures from when it was due, not when we got round
> to sending it. So the chart cannot flatter us.**
>
> Reading it: green is inside budget, red is outside, the dashed line is the
> fifty milliseconds. We hold the budget to a hundred requests per second on a
> single instance. Throughput keeps up to two hundred — look at the "served"
> row — but the latency budget doesn't.
>
> **And past that it doesn't plateau, it collapses. At eight hundred offered we
> serve seventy-two. More load, less work done. That's a system that doesn't
> recover from a spike on its own, which is why admission control is on our next
> list.**

---

## Slide 20 — What Load Testing Exposed

> Three things, and I want to be straight about all three, because the first one
> is us correcting ourselves.
>
> **At the last review we said the gateway responds in half a millisecond.** That
> number was real, but it was measuring the wrong thing — it was our internal
> timer, and that timer stops before we write the audit record, which is the most
> expensive part of the request. The number a caller actually experiences at the
> ceiling is forty-nine milliseconds. Still inside budget — but it is ninety-eight
> percent of the budget, not one percent, and we would rather tell you that than
> have you find it.
>
> Second: the audit chain was dropping records under concurrency. That's the next
> slide.
>
> Third, and this is the one we found most interesting. **Under overload this
> system doesn't just get slow — it starts giving different answers.** When the
> engines exceed their twenty-millisecond timeout, they're dropped from the
> calculation by design, the trust score is computed from fewer signals, and
> around thirteen percent of verdicts flip from ALLOW to REVIEW — on traffic an
> idle gateway would have approved. Same model, same code, same config. Only the
> arrival rate changed.
>
> That is our safety design working correctly. But it means a traffic spike
> quietly turns automatic approvals into a human review queue, and an operations
> team needs to know that in advance rather than discover it.

---

## Slide 21 — Case Study: the Audit Log That Lied

> I want to spend a minute on one defect, because how we handled it says more
> than the fact we found it.
>
> Our strongest claim is tamper-evident evidence for every decision. Under
> concurrent writes we were losing entries — two out of ninety-six. And here is
> the part that actually worried us: **the verification endpoint still reported
> the chain intact.** A hash chain detects a record that was *changed*. It cannot
> detect a record that was never written, because the remaining links are still
> consistent with each other. So our own audit tool was giving a green light on
> an incomplete log.
>
> **The tempting fix was a lock inside the application. We measured before we
> fixed, and it's a good thing we did.** With one server process there were zero
> losses — the event loop was already forcing those writes into a queue. The
> losses only appeared with four processes. Which means an in-application lock
> would have protected the one configuration that was never broken, and done
> nothing for the one that was, because those four processes can't see each
> other's locks.
>
> So the lock had to go where all four processes meet — the database. A
> per-tenant advisory lock, taken before we read the end of the chain. Plus
> randomised backoff on retries, because the original code retried instantly,
> which kept all the racers in lockstep colliding with each other.
>
> **Result: zero losses from two writers up to forty-eight. And throughput
> doubled, because the retry storm we removed was itself a large part of the
> load.**
>
> The lesson we'd like to leave you with is the measurement step. The obvious fix
> was the wrong fix, and only measuring where the bug actually lived told us that.

---

## Slide 22 — Contributions and Conclusion

> Our contributions are split across architecture and the drift engine, the
> services and audit trail, and the SDK, dashboard and testing.
>
> To close. 274 tests passing. The fifty-millisecond budget verified under real
> load to a hundred requests per second, honestly measured. Two concurrency
> defects that our own harness found and that we fixed. And an audit trail that
> caught real tampering in front of you.
>
> **We'd rather show you a system we've stress-tested and found faults in than a
> system nobody has pushed hard enough to break.**
>
> For Review-2: admission control, so a spike sheds load at the door instead of
> silently filling a review queue; the Lending Club replay on two million real
> loans; model and data versioning; and moving the audit write off the hot path
> so we can re-measure against PostgreSQL rather than SQLite.
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
| **Calibration** | Feeding in a change whose size you already know, to check the instrument reads correctly. How you validate a thermometer. |
| **Monotonicity** | More drift in must always mean a bigger number out. If that can ever go backwards, the score can't be trusted. |
| **Coordinated omission** | The trap where a load tester slows down when the server does, so it never samples the slow part and reports a far better p99 than the truth. |
| **Open-loop generator** | A load tester that sticks to a fixed schedule no matter how the server behaves — which is what avoids that trap. |
| **Congestion collapse** | Past a certain load the system does *less* work, not the same amount. A spike leaves it stuck there. |
| **Advisory lock** | Asking the database to let only one process at a time into a piece of code. Works across processes, unlike a lock inside one program. |
| **Jittered backoff** | Waiting a random moment before retrying, so everyone who just collided doesn't collide again in lockstep. |

---

# Likely questions

**"Where is your dataset?"** — *slides 16-18; full argument in `docs/DATASET.md`*
> Two kinds, for two different questions. Custos has no trained model in it, so
> it's an instrument, and instruments are validated by calibration: you feed in a
> change whose size you chose, and check the reading. Zero shift reads 0.030 —
> stable. A one-sigma shift reads 1.019 — four times the industry's "significant"
> threshold. That proves the measurement is *correct*, and it's the only thing
> that can, because on real data nobody knows the true answer to compare against.
> Then separately, real data proves it fires on drift nobody chose — our replay
> harness works on any time-ordered CSV, and running it on the two-million-row
> Lending Club set is our next step.

**"Isn't generating your own data circular?"**
> It would be if we were claiming predictive accuracy. We're claiming measurement
> accuracy, and for that, chosen inputs are *stronger* evidence, because the true
> answer exists and can be checked. The circular version would be tuning the
> detector until it produced a pleasing number on real data — that's the thing we
> specifically don't do.

**"Why not a standard benchmark like MNIST or Adult?"**
> They're shuffled and have no time axis. Drift is a property of *ordered* data —
> with no time dimension there is no drift to detect. That's exactly why Lending
> Club is the right target: a real time axis, and a documented regime change in
> 2008 and again in 2016.

**"How much data does it need?"**
> Thirty samples minimum before a window is scored at all, two hundred in the
> replay harness. Below that, PSI is measuring sampling noise. It reports
> "insufficient data" rather than a number it can't stand behind.

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

**"Is half a millisecond realistic?"** — *(if they remember it from last time)*
> It isn't, and we corrected it ourselves. Half a millisecond was our internal
> timer, which stops before the audit write. Measured properly, from the caller's
> side, it's forty-nine milliseconds at our ceiling of a hundred requests per
> second — inside the budget, but using almost all of it. The full method and raw
> numbers are in `benchmarks/README.md`.

**"Your load test is on SQLite and one core. Isn't that meaningless for production?"**
> It's a floor, not a ceiling, and we label it that way on the chart. SQLite
> serialises every write and fsyncs each audit append, so it's the pessimistic
> case. The harness takes a `--database-url`, so the same sweep runs against
> PostgreSQL unchanged — that measurement plus moving the audit write off the hot
> path is on our Review-2 list. What we'd defend today is the *method*, and the
> three defects it found, which are not database-specific.

**"You only tested to 800 requests per second."**
> We stopped where the answer stopped changing. From four hundred upward the
> system is already in congestion collapse, so higher rates tell us the same
> thing more expensively. The interesting region is between fifty and two
> hundred, and we sampled it.

**"How do you know your fix actually worked?"**
> The same harness that found it. It went from two entries lost in ninety-six to
> zero, and we pushed it to forty-eight concurrent writers — six times the level
> where the failure started — and through the real gateway on four worker
> processes, which is where the bug actually lived. Those checks are committed as
> tests, so a regression fails the build rather than waiting for the next review.

**"Why three verdicts instead of two?"**
> Because in lending, full automation is too risky and full manual review is too
> expensive. The middle answer is what makes it usable — and the practitioner we
> interviewed said exactly that: "you need some human eye to validate everything."
