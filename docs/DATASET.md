# Data and Validation

> How Custos is validated, why it is validated that way, and what data it uses.

This document exists because "where is your dataset?" is the first question a
reviewer should ask of any project that touches machine learning — and because
the honest answer here needs more than one sentence.

---

## 1. The short answer

Custos is validated on **two kinds of data, for two different reasons**:

| | Data | Question it answers | Ground truth |
|---|---|---|---|
| **Calibration** | Controlled distributions with injected shifts of known size | *Is the detector correct?* | **Known** — we chose the shift |
| **Field** | Public real-world credit datasets, replayed in time order | *Does it fire on drift that actually happened?* | **Unknown** — but the drift is real |

Neither is sufficient alone. Together they are the standard way any measuring
instrument is validated.

---

## 2. Why this project is not a "dataset project"

This is the distinction the whole defence rests on, so it is worth stating
precisely.

**Custos does not learn anything from data.** It contains no trained model, no
fitted parameters, no weights. It is a **measuring instrument**: it takes two
distributions and reports how far apart they are, using two published
statistics (PSI and the two-sample Kolmogorov–Smirnov statistic).

That changes what "validation" means:

- A **model** is validated on a dataset, because the question is *"does it
  predict correctly on data it has not seen?"* — and only real, held-out data
  can answer that.
- An **instrument** is validated by **calibration**, because the question is
  *"does it measure correctly?"* — and that requires inputs whose true value is
  **already known**.

You do not validate a thermometer by pointing it at random objects and hoping.
You put it in melting ice and check it reads 0 °C, then in boiling water and
check it reads 100 °C. The reference points must be *known*, or the reading
cannot be checked against anything.

Drift detection is the same. If PSI is run over a real dataset and returns
`0.34`, there is no way to know whether `0.34` is right — nobody knows the true
amount of drift in that data. Run it over a distribution shifted by a known one
standard deviation, and the answer can be checked.

**This is why controlled data is not a shortcut here. It is the only way to
establish that the detector is correct at all.**

---

## 3. What the controlled validation actually proves

`examples/fintech_demo/inject_drift.py` produces three scenarios drawn directly
from what practitioners described in interview (`docs/conversations/`):

| Scenario | What it simulates | What it must prove |
|---|---|---|
| `population_shift` | A downturn — incomes fall, utilisation rises | Detector fires, and names the features that moved |
| `pipeline_break` | An upstream feed dies; a feature pins to one value | Detector fires, and names *that* feature specifically |
| `gradual` | Slow month-over-month movement | Detector fires against a **fixed** baseline, where a rolling baseline would miss it entirely |

These are backed by **43 unit tests** over the detectors and severity roll-up,
including:

- **Golden values.** PSI is checked against a figure computed by hand from the
  definition (`test_golden_value_two_buckets`), and KS against a case where the
  CDF gap is exactly 0.5 by construction. If the implementation were wrong,
  these fail.
- **Industry band agreement.** A 1σ mean shift must read above PSI 0.25
  ("significant"), and two draws from the *same* distribution must read below
  0.10 ("stable"). This proves the numbers mean what a credit-risk team already
  expects them to mean.
- **Monotonicity, exhaustively.** Over 500 randomised perturbations, increasing
  any feature's drift can never lower the reported severity. This is the
  invariant that makes the whole score trustworthy.
- **Refusal to guess.** An empty sample raises rather than returning `0.0`,
  because reporting "no drift" for "no data" is the exact failure the system
  exists to prevent.

Not one of these could be demonstrated on real data, because on real data
**there is no known answer to check against.**

---

## 4. The field validation, and how to run it

`examples/datasets/replay.py` replays **any** real, time-ordered CSV through the
same drift code the gateway uses — not a reimplementation of it. The earliest
window becomes the fixed baseline; every later window is scored against it,
which is exactly what happens in production.

```bash
python -m examples.datasets.replay lending_club.csv \
    --time-column issue_d \
    --features loan_amnt,annual_inc,dti,revol_util,fico_range_low
```

### Recommended dataset: Lending Club (2007–2018)

- ~2.2 million real consumer loans with genuine, externally-caused distribution
  shift across the 2008 financial crisis and Lending Club's 2016 credit policy
  change.
- Publicly available; not bundled here because it is ~600 MB and separately
  licensed.
- Nobody chose the drift in it, which is exactly what makes it a fair test.

### Alternatives

| Dataset | Rows | Note |
|---|---|---|
| Give Me Some Credit (Kaggle) | 150k | No time column — use `--window-rows` |
| UCI Default of Credit Card Clients | 30k | Smaller; good for a quick check |
| UCI German Credit | 1k | Too small for stable PSI; illustrative only |

**Status:** the harness is written, tested and dataset-agnostic. Running it on
Lending Club and reporting the drift timeline is stated in the deck as
Review-2 work, and it is the single highest-value item on that list.

---

## 5. The demonstration model

`examples/fintech_demo/model/train.py` is a logistic regression trained on
4,000 generated applicants (85.4% training accuracy).

**It is a fixture, not a contribution.** Its only job is to be a plausible thing
for Custos to sit in front of. It is deliberately pure-Python with JSON weights
so that it cannot break, cannot execute code on load, and needs no scientific
computing stack.

If a reviewer asks whether the *model* is any good, the honest answer is: it
does not matter, and swapping it for a real one would change nothing about what
Custos does. Custos never sees the model — only the feature vectors going into
it.

---

## 6. Anticipated questions

**"You generated your own data. Isn't that circular?"**
It would be if we were claiming predictive accuracy. We are claiming
measurement accuracy, and for that, generated data is *stronger* evidence,
because the true answer is known and can be checked. The circular version would
be tuning the detector until it produced a pleasing number on real data — which
is what we specifically avoid.

**"Then why bother with real data at all?"**
Because calibration proves the instrument is correct, not that it is *useful*.
Real data proves the thresholds fire on drift that occurs naturally, at rates
an operator can live with. That is a separate claim and needs separate evidence.

**"Why not just use a standard ML benchmark?"**
Benchmarks like MNIST or Adult are shuffled and have no time axis. Drift is a
property of *ordered* data — without a time dimension there is no drift to
detect. This is why the Lending Club set is the right choice: it has a real
time axis and a real, documented regime change in it.

**"How much data does it need to work?"**
`MIN_SAMPLES = 30` before a window is scored at all, and `MIN_WINDOW = 200` in
the replay harness. Below that, PSI is dominated by sampling noise rather than
by any real change. The system reports "insufficient data" rather than
producing a number it cannot stand behind.

**"What about the drift you can't see?"**
Custos measures *input* drift — the features going into the model. It does not
measure label drift or concept drift, because production labels arrive weeks or
months later, if ever. This is a stated limitation, not an oversight: it is
precisely why the practitioners interviewed rely on input monitoring as a
leading indicator.
