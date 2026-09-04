"""Inject synthetic drift into the demo data stream.

Three scenarios, because they are the three the practitioners interviewed for
this project actually described (docs/conversations/01, 02) — and because
Custos should behave differently for each:

  population_shift  a genuine change in who is applying (a downturn). The model
                    is now scoring people it was not trained on.
  pipeline_break    an upstream feed dies and a feature pins to a constant.
                    Nothing about the population changed; the data is broken.
  gradual           slow month-over-month movement. The case that is invisible
                    if you compare each window to the previous one, which is
                    exactly why baselines are fixed at registration (ADR 0002).
"""

from __future__ import annotations

import random

from examples.fintech_demo.model.train import TRAINING_POPULATION, sample_applicant

SCENARIOS = ("population_shift", "pipeline_break", "gradual")


def clean_batch(n: int = 200, seed: int | None = None) -> list[dict[str, float]]:
    """Traffic drawn from the training population — the 'nothing is wrong' case."""
    rng = random.Random(seed)
    return [sample_applicant(rng) for _ in range(n)]


def population_shift(n: int = 200, severity: float = 1.0, seed: int | None = None):
    """A downturn: incomes fall, utilisation climbs, tenure shortens.

    Bureau score is left alone on purpose. A drift signal that blames every
    feature whenever anything moves is not actionable — the per-feature
    breakdown has to be able to point at the ones that actually moved.
    """
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        row = sample_applicant(rng)
        row["income"] -= 30000 * severity
        row["utilisation"] += 0.40 * severity
        row["months_employed"] -= 30 * severity
        rows.append(row)
    return rows


def pipeline_break(n: int = 200, feature: str = "bureau_score", seed: int | None = None):
    """An upstream feed dies and the feature pins to a single default value.

    This is the failure the interviewees said they see most often in production
    — and it is not distribution drift in any meaningful sense, even though PSI
    reports it loudly. Telling the two apart is the operator's job; Custos's job
    is to make it impossible to miss.
    """
    rng = random.Random(seed)
    default_value = TRAINING_POPULATION[feature][0]
    rows = []
    for _ in range(n):
        row = sample_applicant(rng)
        row[feature] = default_value
        rows.append(row)
    return rows


def gradual(n: int = 200, step: int = 0, steps: int = 6, seed: int | None = None):
    """One slice of a slow shift, ``step`` of ``steps``."""
    return population_shift(n=n, severity=(step + 1) / steps, seed=seed)


def build(scenario: str, n: int = 200, seed: int | None = None) -> list[dict[str, float]]:
    if scenario == "population_shift":
        return population_shift(n=n, seed=seed)
    if scenario == "pipeline_break":
        return pipeline_break(n=n, seed=seed)
    if scenario == "gradual":
        return gradual(n=n, step=steps_default(), seed=seed)
    if scenario == "clean":
        return clean_batch(n=n, seed=seed)
    raise ValueError(f"unknown scenario {scenario!r}; expected one of {SCENARIOS + ('clean',)}")


def steps_default() -> int:
    return 5


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=[*SCENARIOS, "clean"])
    parser.add_argument("-n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    for row in build(args.scenario, n=args.n, seed=args.seed):
        print(json.dumps({k: round(v, 2) for k, v in row.items()}))
