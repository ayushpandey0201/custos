# Gating study — pre-registered protocol (`gating-v1`)

> Written and committed **before any real-data run**. Its job is to make it
> impossible to quietly tune the study toward a pleasing answer. Anything changed
> after the first Lending Club run must be recorded in the deviation log at the
> bottom, with the date and the reason.

## Question

When a deployed credit model drifts, **which decisions should a human review**, and
**how many bad decisions does each review catch?**

Custos today gates on *population* drift: when the live population moves away from
the training baseline, decisions are escalated. This study measures whether that
helps, against simpler baselines and against per-request alternatives, on real loans
with real outcomes.

## Data and population

- **Dataset:** Lending Club accepted loans, 2007–2018 (`accepted_2007_to_2018Q4.csv.gz`).
- **Term:** 36-month loans only.
- **Censoring guard:** a loan is included only if its term ended by the data snapshot
  (December 2018), so 36-month loans issued after December 2015 are excluded. Without
  this, recent cohorts would contain mostly early defaulters and early payoffs, and
  their default rate would be biased.
- **Outcome:** `bad = 1` for *Charged Off*, *Default*, and *Does not meet the credit
  policy. Status:Charged Off*; `bad = 0` for *Fully Paid* and its credit-policy twin.
  Unresolved statuses (*Current*, *Late*, *In Grace Period*) are excluded and counted.
- **Features:** only fields known at origination — `loan_amnt, annual_inc, dti,
  revol_util, fico_range_low, int_rate, inq_last_6mths, delinq_2yrs, open_acc`. This is
  enforced by an allowlist in `data.py`; anything describing how the loan *performed*
  (payments, recoveries, last FICO pull) cannot be selected.

## Split

- **Train:** issued up to December 2011.
- **Evaluate:** January 2012 to December 2015, in calendar quarters.

## Model

L2-regularised logistic regression (λ = 1.0) on `log1p`-transformed `annual_inc` and
`loan_amnt`, with all features standardised using training statistics. It is fit
once on the training window and never refit. A model that is never updated is the
situation Custos exists for.

## Strategies

Each strategy assigns every evaluation decision a review priority. All use only
information available when the decision is made:

| Name | Review first… |
|---|---|
| `random` | at random — the floor; precision equals the base default rate |
| `model_risk` | highest predicted default probability |
| `low_confidence` | predictions closest to 0.5 (selective-prediction baseline) |
| `population_drift` | loans in windows whose **previous** window drifted most — Custos today |
| `novelty` | loans furthest from the training data (Mahalanobis distance) |
| `risk_plus_novelty` | equal blend of risk and novelty, each as a training-set percentile |
| `custos_adaptive` | **proposed:** blend weighted by the lagged population drift severity *s*: `s·novelty + (1−s)·risk`. Trust the model's own risk when the population is stable; lean on novelty as it drifts |

Drift severity is lagged by one window (`--severity-lag 1`) so that no strategy uses a
window's drift before that window has finished.

When the base default rate is far below 0.5, `low_confidence` reduces to `model_risk`,
because the least confident predictions are then the riskiest ones. It is kept because
it is the canonical selective-prediction baseline, and a reviewer will expect to see it.

## Pilot (synthetic data, before any real data)

The harness was first run on `synthetic.py` data with a planted shift. One protocol
change came out of that run, before any Lending Club data was loaded:

- **H4 was originally stated on AUC.** On the pilot, drift tracked the default rate
  strongly (ρ = 0.77) but not AUC (ρ = −0.02). The model went on *ranking* borrowers
  correctly while its predicted default rate fell far below the real one (~17%
  predicted against ~30% actual). That is real harm, and AUC cannot see it. H4 is
  therefore stated on the calibration gap; AUC remains a reported secondary measure.

The pilot also showed population-drift gating at lift ≈ 1.0 even under strong
persistent drift. It ranks periods, not decisions, and when most periods are drifted
the periods stop discriminating. This is reported as a pilot observation. No strategy
was changed because of it.

## Budgets and metrics

- **Review budgets:** 1%, 2%, 5%, 10%, 20% of evaluation decisions. **Primary: 5%.**
- **Defaults caught per 1,000 reviews**, with a 95% Wilson interval.
- **Recall:** the share of all evaluation defaults that fall inside the reviewed set.
- **Lift:** precision ÷ base default rate.
- **Principal at risk caught:** loan amount of the defaults caught; principal loss
  caught where repayment columns are present.
- **Drift vs harm:** Spearman ρ across evaluation windows between drift severity and
  the model's **calibration gap**, |actual default rate − mean predicted risk|. A
  10,000-permutation two-sided p-value is reported. The window default rate and AUC
  are reported as secondary measures.

## Hypotheses and decision rules

Evaluated at the primary 5% budget. "Separated" means the 95% Wilson intervals do not
overlap. That is a conservative test, because the strategies are scored on the same
loans.

| | Hypothesis | Supported if | Contradicted if |
|---|---|---|---|
| **H1** | Population-drift gating beats random review | its lower bound > base rate | its upper bound < base rate |
| **H2** | Per-request novelty beats population-drift gating | separated, novelty higher | separated, novelty lower |
| **H3** | `custos_adaptive` beats `model_risk`, the strongest naive baseline | separated, adaptive higher | separated, adaptive lower |
| **H4** | Population drift predicts model error | ρ(severity, calibration gap) > 0 and p < 0.05 | ρ < 0 and p < 0.05 |

Anything else is **inconclusive**. Every outcome is reported, including those that
contradict a hypothesis.

## What each outcome means, decided now

- **H1 contradicted or inconclusive:** population-drift gating, which is how Custos
  works today, has no demonstrated value on this data. The paper then reports that as
  a finding, and the product's gating logic changes.
- **H3 inconclusive or contradicted:** there is no method contribution. The paper
  becomes an empirical comparison, with no claim of a new method.
- **H4 contradicted:** drift on this data does not track model error. This is the
  most important negative result possible, because it challenges the premise of
  label-free drift gating.

## Known limitations, stated in advance

1. **Hindsight budget.** The top 5% is taken over the whole evaluation period. The
   scores are causal, but the cut-off is not. A causal, rolling-threshold variant is
   planned for v2.
2. **Reviews are assumed perfect.** A reviewed default counts as caught. These numbers
   are an upper bound on what review could prevent.
3. **Only accepted loans.** Lending Club publishes outcomes only for loans it funded,
   so nothing can be said about applicants it rejected.
4. **Platform changes confound drift.** Lending Club changed its credit policy over
   these years, so "drift" here includes policy changes, not only economic ones.
5. **One dataset.** A second time-ordered credit dataset with outcomes is required
   before any general claim.

## Running

```bash
python -m experiments.gating.run data/accepted_2007_to_2018Q4.csv.gz \
    --json experiments/results/lending_club_gating_v1.json
```

Smoke-test on synthetic data in the same schema, before the real file exists:

```bash
python -m experiments.gating.synthetic data/synthetic_lending_club.csv.gz
python -m experiments.gating.run data/synthetic_lending_club.csv.gz
```

## Deviation log

Every change made after the first real-data run, with the date and the reason.

| Date | Change | Reason |
|---|---|---|
| — | — | — |
