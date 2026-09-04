# Fintech demo

★ **Kept working at all times.** Breaking this is treated as breaking the main build. ★

It is four things at once: the pilot demo, the onboarding tutorial, the e2e test fixture, and the
answer to "does Custos actually do anything?".

## Run it

```bash
python -m examples.fintech_demo.run_demo
```

No arguments, no infrastructure, ~30 seconds. Add `--serve` to leave the gateway and control plane
running afterwards on ports 8000/8001 so the dashboard can connect.

## What it shows

A lending bot auto-approves loan applications using a credit-risk model. Custos gates the
disbursement.

| Act | Situation | Verdict | Why it matters |
|---|---|---|---|
| 1 | Model never registered | **REVIEW** | Unknown ≠ safe. Custos escalates rather than guessing (ADR 0005). |
| 2 | Registered, baselined, healthy traffic | **ALLOW** (trust 0.99) | The normal case has to be frictionless or nobody adopts it. |
| 3 | Incomes fall 50%, utilisation doubles | severity 0.02 → **0.83** | Per-feature attribution names `utilisation` and `income`; `bureau_score` did not move and is not blamed. |
| 4 | Identical application, identical code | **REVIEW** (trust 0.48) | The verdict changed because the *world* changed. No deploy, no config edit. |
| 5 | 900k disbursement vs. a 500k policy rule | **BLOCK** | A veto overrides every other signal. |
| 5b | Someone edits the BLOCK record to say ALLOW | **chain broken at #604** | Tamper-evidence, demonstrated rather than asserted. |

## The pieces

| File | What it is |
|---|---|
| `model/train.py` | Pure-Python logistic regression credit model. No sklearn, no XGBoost, no pickle — a fixture that needs a scientific stack to load is one that eventually stops loading. |
| `agent/loan_bot.py` | The integration. Custos costs this agent four lines. |
| `inject_drift.py` | Three drift scenarios: `population_shift`, `pipeline_break`, `gradual`. |
| `run_demo.py` | The narrated five-act runner. |

## Why three drift scenarios

They come from practitioner interviews (`docs/conversations/`), and Custos should behave
differently for each:

- **`population_shift`** — a real change in who is applying. The model is now scoring people it
  was not trained on. Legitimate cause for lowering trust.
- **`pipeline_break`** — an upstream feed dies and a feature pins to a constant. *Nothing about
  the population changed; the data is broken.* PSI screams, and it should — but the fix is an
  engineering fix, not a modelling one. Per-feature attribution is what lets an operator tell
  these apart.
- **`gradual`** — slow month-over-month movement. Invisible if you compare each window to the
  previous one, which is exactly why baselines are fixed at registration (ADR 0002).

Try them directly:

```bash
python -m examples.fintech_demo.inject_drift pipeline_break -n 5
```
