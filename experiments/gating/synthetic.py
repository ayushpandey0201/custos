"""Synthetic loans in Lending Club's schema, with a planted answer.

    python -m experiments.gating.synthetic data/synthetic_lending_club.csv.gz

Two jobs:

1. Smoke-test the whole study before the real file has been downloaded.
2. Calibrate the harness itself. Because the tests know exactly what was
   planted, they can check the harness finds it — the same discipline used for
   the drift detector (known input, checkable output), applied one level up.

What is planted:

* 2009–2012: a stable population. Default risk rises smoothly with low FICO,
  high DTI and recent credit enquiries — the kind of relationship a logistic
  model learns well.
* From 2013, a quarter of applicants are **over-limit borrowers**: revolving
  utilisation of 101–140%, a range never seen in training, where utilisation is
  at most 100%. Their true default risk is far higher than a linear model
  extrapolating from the training range will predict.

So population drift should appear from 2013, `model_risk` should underestimate
the new segment, and `novelty` should find it. The file also contains 60-month
loans, 36-month loans too recent to have matured, and unresolved statuses, so
every exclusion rule in data.py is exercised.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import math
import random
from datetime import datetime
from pathlib import Path

from experiments.gating.data import DEFAULT_SNAPSHOT

COLUMNS = [
    "id", "issue_d", "term", "loan_status", "loan_amnt", "funded_amnt", "annual_inc",
    "dti", "revol_util", "fico_range_low", "int_rate", "inq_last_6mths", "delinq_2yrs",
    "open_acc", "total_rec_prncp", "recoveries", "total_pymnt",
]

SHIFT_FROM = 2013
OVER_LIMIT_SHARE = 0.25
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def applicant(rng: random.Random, over_limit: bool) -> dict[str, float]:
    fico = 5 * round(_clamp(rng.gauss(705, 35), 640, 850) / 5)
    return {
        "fico_range_low": fico,
        "annual_inc": round(_clamp(math.exp(rng.gauss(math.log(62_000), 0.5)), 12_000, 600_000)),
        "dti": round(_clamp(rng.gauss(17, 7), 0, 40), 2),
        "revol_util": round(
            rng.uniform(101, 140) if over_limit else _clamp(rng.gauss(52, 22), 0, 100), 1
        ),
        "loan_amnt": 25 * round(
            _clamp(math.exp(rng.gauss(math.log(12_000), 0.6)), 1_000, 35_000) / 25
        ),
        "inq_last_6mths": rng.choices(range(6), weights=(45, 28, 14, 7, 4, 2))[0],
        "delinq_2yrs": rng.choices(range(4), weights=(82, 12, 4, 2))[0],
        "open_acc": int(_clamp(rng.gauss(11, 4), 2, 40)),
        "int_rate": round(_clamp(26 - (fico - 640) * 0.075 + rng.gauss(0, 1.5), 5.3, 28.99), 2),
    }


def true_default_probability(a: dict[str, float], over_limit: bool) -> float:
    z = (
        -1.9
        - 0.014 * (a["fico_range_low"] - 705)
        + 0.035 * (a["dti"] - 17)
        + 0.18 * a["inq_last_6mths"]
        + 0.15 * a["delinq_2yrs"]
        + 0.004 * (a["revol_util"] - 52)
        + 0.10 * math.log(a["loan_amnt"] / 12_000)
        - 0.20 * math.log(a["annual_inc"] / 62_000)
    )
    if over_limit:
        z += 2.2  # the cliff a model trained inside 0–100% never sees
    return 1 / (1 + math.exp(-z))


def _matured(year: int, month: int, term: int, snapshot: datetime) -> bool:
    total = year * 12 + month - 1 + term
    return datetime(total // 12, total % 12 + 1, 1) <= snapshot


def generate(
    path: Path,
    per_month: int = 600,
    years: tuple[int, int] = (2009, 2016),
    seed: int = 20261016,
    snapshot: datetime = DEFAULT_SNAPSHOT,
) -> int:
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for year in range(years[0], years[1] + 1):
            for month in range(1, 13):
                for _ in range(per_month):
                    term = 36 if rng.random() < 0.75 else 60
                    over = year >= SHIFT_FROM and rng.random() < OVER_LIMIT_SHARE
                    a = applicant(rng, over)
                    bad = rng.random() < true_default_probability(a, over)
                    funded = a["loan_amnt"]

                    if not _matured(year, month, term, snapshot):
                        status = ("Charged Off" if bad and rng.random() < 0.6
                                  else "Fully Paid" if rng.random() < 0.2 else "Current")
                    elif rng.random() < 0.01:
                        status = "Late (31-120 days)"
                    elif bad:
                        status = ("Does not meet the credit policy. Status:Charged Off"
                                  if year < 2010 and rng.random() < 0.3 else "Charged Off")
                    else:
                        status = "Fully Paid"

                    repaid = funded if not bad else round(funded * rng.uniform(0.05, 0.6), 2)
                    recovered = round(funded * rng.uniform(0, 0.1), 2) if bad else 0.0
                    writer.writerow(
                        [
                            written + 1,
                            f"{MONTHS[month - 1]}-{year}",
                            f" {term} months",
                            status,
                            funded,
                            funded,
                            a["annual_inc"],
                            a["dti"],
                            f"{a['revol_util']}%",
                            a["fico_range_low"],
                            f" {a['int_rate']}%",
                            a["inq_last_6mths"],
                            a["delinq_2yrs"],
                            a["open_acc"],
                            repaid,
                            recovered,
                            round(repaid * 1.15, 2),
                        ]
                    )
                    written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--per-month", type=int, default=600)
    parser.add_argument("--seed", type=int, default=20261016)
    args = parser.parse_args(argv)
    n = generate(args.out, per_month=args.per_month, seed=args.seed)
    print(f"wrote {n:,} synthetic loans to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
