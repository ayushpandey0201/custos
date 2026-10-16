"""Load Lending Club into a leakage-free, censoring-safe study population.

The rules this module enforces are in PROTOCOL.md. They are enforced in code
rather than left to convention because each one, if broken, produces numbers
that look excellent and mean nothing:

* **Leakage.** Lending Club ships dozens of columns describing what happened
  *after* the loan was made — total payments, recoveries, the last FICO pull.
  Any of them as a feature lets a model "predict" defaults it has already seen.
  Features therefore come from an allowlist of origination-time fields, and
  anything else is refused.
* **Censoring.** A loan issued in 2017 had barely started repaying when the
  data was published. Among such loans, the ones that have already resolved are
  mostly early defaulters and early payoffs. Including them biases recent
  cohorts. A loan is kept only if its term ended by the snapshot date.
* **Unresolved outcomes.** "Current" or "Late" is not an outcome. Such loans
  are excluded, and counted, rather than guessed.
"""

from __future__ import annotations

import csv
import gzip
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from examples.datasets.replay import parse_time

# Fields known when the lending decision is made. The only legal features.
ORIGINATION_FEATURES = (
    "loan_amnt",
    "annual_inc",
    "dti",
    "revol_util",
    "fico_range_low",
    "int_rate",
    "inq_last_6mths",
    "delinq_2yrs",
    "open_acc",
)

BAD_STATUSES = frozenset(
    {
        "Charged Off",
        "Default",
        "Does not meet the credit policy. Status:Charged Off",
    }
)
GOOD_STATUSES = frozenset(
    {
        "Fully Paid",
        "Does not meet the credit policy. Status:Fully Paid",
    }
)

# The Kaggle file is a snapshot taken at the end of 2018.
DEFAULT_SNAPSHOT = datetime(2018, 12, 1)


@dataclass(frozen=True, slots=True)
class Loan:
    issued: datetime
    x: tuple[float, ...]  # raw origination features, in Study.features order
    bad: int  # 1 if charged off / defaulted
    principal: float  # loan amount: the exposure a review could protect
    loss: float | None  # principal actually lost, where repayment columns exist


@dataclass
class Study:
    features: tuple[str, ...]
    loans: list[Loan]
    rows_read: int
    excluded: dict[str, int] = field(default_factory=dict)


def check_features(features: tuple[str, ...]) -> None:
    """Refuse anything that is not known at origination."""
    illegal = [f for f in features if f not in ORIGINATION_FEATURES]
    if illegal:
        raise ValueError(
            f"not origination-time features (would leak the outcome): {illegal}. "
            f"Allowed: {', '.join(ORIGINATION_FEATURES)}"
        )
    if len(set(features)) != len(features):
        raise ValueError("duplicate features")


def _number(raw: str | None) -> float | None:
    """'13.56%' -> 13.56; '' or 'n/a' or inf -> None."""
    text = (raw or "").strip().rstrip("%").strip()
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _term_months(raw: str | None) -> int | None:
    """' 36 months' -> 36."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    return int(digits) if digits else None


def _months_after(moment: datetime, months: int) -> datetime:
    total = moment.year * 12 + (moment.month - 1) + months
    return datetime(total // 12, total % 12 + 1, 1)


def _open(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    return opener(path, "rt", newline="", encoding="utf-8", errors="replace")


def _find_header(reader) -> list[str]:
    """The header row, skipping the notes line some Lending Club exports start with."""
    for _ in range(5):
        row = next(reader, None)
        if row is None:
            break
        if "issue_d" in row and "loan_status" in row:
            return row
    raise ValueError("no header with issue_d and loan_status in the first five rows")


def load(
    path: Path,
    features: tuple[str, ...] = ORIGINATION_FEATURES,
    term: int = 36,
    snapshot: datetime = DEFAULT_SNAPSHOT,
    progress: bool = False,
) -> Study:
    check_features(features)
    excluded = {
        "unparseable_date": 0,
        "other_term": 0,
        "not_matured": 0,
        "unresolved_status": 0,
        "missing_feature": 0,
    }
    loans: list[Loan] = []
    rows = 0

    with _open(path) as handle:
        reader = csv.reader(handle)
        header = _find_header(reader)
        col = {name: i for i, name in enumerate(header)}
        for needed in ("issue_d", "loan_status", "term", *features):
            if needed not in col:
                raise ValueError(f"column {needed!r} missing from {path.name}")
        feature_idx = [col[f] for f in features]
        has_loss = all(c in col for c in ("funded_amnt", "total_rec_prncp", "recoveries"))
        width = len(header)

        for row in reader:
            if len(row) < width:  # summary / footer lines
                continue
            rows += 1
            if progress and rows % 250_000 == 0:
                print(f"  … {rows:,} rows read", flush=True)

            issued = parse_time(row[col["issue_d"]].strip())
            if issued is None:
                excluded["unparseable_date"] += 1
                continue
            if _term_months(row[col["term"]]) != term:
                excluded["other_term"] += 1
                continue
            if _months_after(issued, term) > snapshot:
                excluded["not_matured"] += 1
                continue

            status = row[col["loan_status"]].strip()
            if status in BAD_STATUSES:
                bad = 1
            elif status in GOOD_STATUSES:
                bad = 0
            else:
                excluded["unresolved_status"] += 1
                continue

            values = [_number(row[i]) for i in feature_idx]
            if any(v is None for v in values):
                excluded["missing_feature"] += 1
                continue

            principal = _number(row[col["loan_amnt"]]) if "loan_amnt" in col else None
            loss = None
            if has_loss:
                funded = _number(row[col["funded_amnt"]])
                repaid = _number(row[col["total_rec_prncp"]])
                recovered = _number(row[col["recoveries"]])
                if None not in (funded, repaid, recovered):
                    loss = max(0.0, funded - repaid - recovered) if bad else 0.0

            loans.append(
                Loan(
                    issued=issued,
                    x=tuple(values),  # type: ignore[arg-type]
                    bad=bad,
                    principal=principal or 0.0,
                    loss=loss,
                )
            )

    return Study(features=features, loans=loans, rows_read=rows, excluded=excluded)
