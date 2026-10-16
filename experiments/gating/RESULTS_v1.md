# Gating study v1 — results on Lending Club

> The confirmatory run of the protocol in `PROTOCOL.md`, executed exactly as
> registered. **There were no deviations.** Raw output:
> `experiments/results/lending_club_gating_v1.json`.

## Provenance

| | |
|---|---|
| Protocol commit | `414e7e3`, pushed to GitHub at 21:44 IST on 16 Oct 2026 |
| Dataset downloaded | 21:54 IST on 16 Oct 2026, ten minutes **after** the protocol was public |
| Dataset | `accepted_2007_to_2018Q4.csv.gz`, 392,582,231 bytes, sha256 `55c16f75120f8976…` (full hash in the JSON) |
| Code state | tracked files identical to `414e7e3`. `git_dirty: true` is caused only by an unrelated untracked `.pptx` |
| Runtime | 56 s, pure Python standard library |

## Population

2,260,701 rows were read and 620,634 were kept. Exclusions: 650,914 loans were not
36-month; 988,585 had not matured by December 2018; 147 had unresolved outcomes;
388 were missing a feature; 33 had no parseable date.

| | Loans | Default rate |
|---|---|---|
| Train (2007–2011) | 31,448 | 12.26% |
| Evaluate (2012–2015) | 589,186 | 14.03% |

Model AUC was 0.677 on training data and 0.664 on evaluation data.

## Defaults caught per 1,000 reviews

| Strategy | 1% | 2% | **5%** | 10% | 20% | Lift @5% |
|---|---|---|---|---|---|---|
| random | 140.3 | 140.3 | **140.3** | 140.3 | 140.3 | 1.00 |
| **model_risk** | 333.0 | 317.0 | **292.5** | 270.4 | 245.9 | **2.08** |
| low_confidence | 333.2 | 317.0 | 292.5 | 270.4 | 245.9 | 2.08 |
| population_drift | 127.6 | 130.4 | **126.2** | 125.0 | 134.7 | **0.90** |
| novelty | 174.5 | 186.2 | 188.2 | 177.7 | 164.9 | 1.34 |
| risk_plus_novelty | 326.4 | 306.4 | 280.5 | 263.9 | 238.8 | 2.00 |
| custos_adaptive | 322.1 | 296.8 | 274.2 | 254.3 | 223.3 | 1.95 |

## Pre-registered hypotheses

| | Claim | Verdict | Evidence at 5% |
|---|---|---|---|
| H1 | Population-drift gating beats random review | **Contradicted** | 126.2 [122.5–130.1] vs 140.3 |
| H2 | Per-request novelty beats population-drift gating | Supported | 188.2 [183.8–192.7] vs 126.2 |
| H3 | `custos_adaptive` beats `model_risk` | **Contradicted** | 274.2 [269.2–279.3] vs 292.5 [287.3–297.7] |
| H4 | Population drift predicts model error | Inconclusive | ρ = 0.21, p = 0.44 over 16 windows |

## What happened

**1. Population drift sent reviewers to the safest loans.** Severity peaked from
2012-Q4 to 2013-Q2 (0.80–0.84), driven mainly by `int_rate`. Those quarters had
*below-average* default rates (12.2–12.9%). At a 5% budget the strategy reviewed
2013-Q2 (all of it) and part of 2013-Q3. Reconstructed by hand from the window
table, that gives 127.0 per 1,000, against 126.2 from the harness. The difference
is within-window sampling.

**2. The drift signal is saturated.** Against a 2007–2011 baseline, 13 of the 16
evaluation quarters fall in the significant band. A signal that says "significant"
almost everywhere cannot rank anything, and it did not track model error (ρ = 0.21,
p = 0.44), the default rate (ρ = −0.04) or AUC (ρ = 0.20).

**3. Real harm happened, and drift could not see which way it went.** The model
*over*estimated risk in 9 quarters (by up to 2.8 points) and *under*estimated it in 7
(by up to 3.2 points, in 2015). Drift severity was high in both regimes.

**4. Unusual is not the same as risky.** On its own, novelty is a weak default
signal (lift 1.34). Because severity was high almost everywhere, `custos_adaptive`
put about three quarters of its weight on novelty, and it scored lower than the
model's own risk ranking. The premise behind it ("when the population drifts, trust
novelty over the model") does not hold on this data.

**5. The model's own risk ranking was best at every budget**, catching about
2.1× the defaults of random review at 5%.

## Consequence for the product: the drift floor

The drift-floor rule added on 16 October (significant drift → REVIEW) would have
escalated **542,276 of 589,186 decisions (92.0%)**. Their default rate was
**14.17%**, against a base rate of 14.03%. That means human review of almost every
loan, for no gain in targeting. The rule is safe, in the sense that it never
auto-approves, but on this evidence it is operationally useless. This is the
product change that H1, as pre-registered, requires.

## What this does and does not show

- It shows that **on Lending Club 2012–2015, population drift measured against a
  fixed historical baseline is a poor guide to which decisions need review.**
- It does **not** show that drift is never useful. Limitation 4 materialised: the
  largest drift is in `int_rate`, which Lending Club itself sets. Much of what was
  measured is the platform repricing, not borrowers changing.
- One dataset. No general claim until a second dataset agrees.
- The registered limitations also apply: the budget is set in hindsight, reviews
  are assumed perfect, and only accepted loans are observed.

## Exploratory next steps

These are **not** confirmatory, and each must be reported as exploratory:

1. Score drift without policy-set fields (`int_rate`), to separate platform
   repricing from population change.
2. Use a rolling recent baseline instead of a fixed 2007–2011 one, to address
   saturation.
3. Look for label-free signals that track the **direction** of miscalibration,
   which population drift could not.
4. Replicate on a second time-ordered credit dataset with outcomes.
5. Replace the hindsight budget with a causal, rolling review threshold.
