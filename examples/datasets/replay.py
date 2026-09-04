"""Replay any real, time-ordered dataset through the Custos drift pipeline.

    python -m examples.datasets.replay data.csv \\
        --time-column issue_d \\
        --features loan_amnt,annual_inc,dti,revol_util

Dataset-agnostic on purpose. Custos does not care what the columns mean; it
needs numeric features and something to order them by. The earliest window
becomes the baseline (the reference the model was "trained" on) and every later
window is scored against it, which reproduces exactly what happens in
production: a fixed reference, and traffic that slowly stops resembling it.

This exists so the drift engine can be validated two ways that answer two
different questions:

  controlled data  — "is the detector correct?"  Ground truth is known because
                     the shift was injected, so a measured PSI can be checked
                     against the shift that produced it. See
                     examples/fintech_demo/inject_drift.py.

  real data        — "does it fire on drift that actually happened?"  Ground
                     truth is unknown, but the drift is real and nobody chose
                     it. That is what this script is for.

Neither alone is sufficient. A detector validated only on injected shifts might
never fire in the wild; a detector validated only on real data cannot be shown
to be *calibrated*, because there is no known answer to compare against.

Datasets this has been written against (all public, none bundled — they are
large and separately licensed):

  Lending Club loan data (2007-2018, ~2.2M rows)
      --time-column issue_d
      --features loan_amnt,annual_inc,dti,revol_util,fico_range_low
      Genuine distribution shift across the 2008 crisis and the 2016 credit
      policy change. The strongest available test for a credit-risk drift
      detector.

  UCI Default of Credit Card Clients (30k rows)
      No native time column; pass --window-rows to split sequentially.

  Give Me Some Credit (Kaggle, 150k rows)
      As above.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

from engines.drift.detectors import ks_test, psi
from engines.drift.severity import compute_severity, feature_severity, severity_band

# Windows smaller than this produce PSI values dominated by sampling noise
# rather than by any real change in the population.
MIN_WINDOW = 200


def read_rows(path: Path, features: list[str], time_column: str | None) -> list[dict]:
    """Load the CSV, keeping only rows where every requested feature is numeric.

    Rows with a missing or non-numeric feature are dropped rather than imputed.
    Imputing here would be dishonest: filling a gap with a mean pulls the
    observed distribution toward the baseline and makes drift look smaller than
    it is — the detector would be measuring our imputation, not the data.
    """
    kept: list[dict] = []
    dropped = 0

    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for raw in csv.DictReader(handle):
            row: dict = {}
            ok = True
            for name in features:
                value = (raw.get(name) or "").strip().rstrip("%")
                try:
                    number = float(value)
                except ValueError:
                    ok = False
                    break
                if not math.isfinite(number):
                    ok = False
                    break
                row[name] = number
            if not ok:
                dropped += 1
                continue
            if time_column:
                row["__t"] = (raw.get(time_column) or "").strip()
            kept.append(row)

    print(f"loaded {len(kept):,} usable rows ({dropped:,} dropped for missing/non-numeric values)")
    return kept


def window_by_time(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group rows by the raw value of the time column, in sorted order."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[row["__t"]].append(row)
    return sorted(buckets.items())


def window_by_count(rows: list[dict], size: int) -> list[tuple[str, list[dict]]]:
    """Split sequentially when the dataset has no usable time column."""
    return [
        (f"rows {i:,}-{i + len(rows[i : i + size]):,}", rows[i : i + size])
        for i in range(0, len(rows), size)
    ]


def columnar(rows: list[dict], features: list[str]) -> dict[str, list[float]]:
    return {name: [r[name] for r in rows] for name in features}


def score(baseline: dict[str, list[float]], live: dict[str, list[float]]) -> tuple[float, dict]:
    """Score one window against the baseline using the production code path.

    Deliberately calls the same ``psi``, ``ks_test`` and ``compute_severity``
    the gateway uses. A replay harness with its own copy of the maths would
    prove nothing about the system that actually runs.
    """
    per_feature: dict[str, dict] = {}
    for name, reference in baseline.items():
        observed = live.get(name)
        if not observed or not reference:
            continue
        try:
            psi_value = psi(reference, observed)
            ks_value = ks_test(reference, observed)
        except ValueError:
            continue
        per_feature[name] = {
            "psi": psi_value,
            "ks": ks_value,
            "severity": feature_severity(psi_value, ks_value),
        }
    if not per_feature:
        return 0.0, {}
    severity = compute_severity({n: s["severity"] for n, s in per_feature.items()})
    return severity, per_feature


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("csv", type=Path, help="path to the dataset")
    parser.add_argument("--features", required=True, help="comma-separated numeric column names")
    parser.add_argument("--time-column", default=None, help="column to order and window by")
    parser.add_argument(
        "--window-rows", type=int, default=0, help="fixed window size when there is no time column"
    )
    parser.add_argument("--top", type=int, default=3, help="features to name per window")
    args = parser.parse_args(argv)

    if not args.csv.exists():
        print(f"no such file: {args.csv}", file=sys.stderr)
        return 1
    if not args.time_column and not args.window_rows:
        print("pass --time-column or --window-rows", file=sys.stderr)
        return 1

    features = [f.strip() for f in args.features.split(",") if f.strip()]
    rows = read_rows(args.csv, features, args.time_column)
    if len(rows) < MIN_WINDOW * 2:
        print(f"need at least {MIN_WINDOW * 2:,} usable rows", file=sys.stderr)
        return 1

    windows = window_by_time(rows) if args.time_column else window_by_count(rows, args.window_rows)
    windows = [(label, w) for label, w in windows if len(w) >= MIN_WINDOW]
    if len(windows) < 2:
        print(f"need at least 2 windows of {MIN_WINDOW:,}+ rows", file=sys.stderr)
        return 1

    baseline_label, baseline_rows = windows[0]
    baseline = columnar(baseline_rows, features)
    print(f"\nbaseline: {baseline_label}  ({len(baseline_rows):,} rows, {len(features)} features)")
    print("every later window is scored against this fixed reference\n")

    print(f"{'window':<24}{'rows':>10}{'severity':>11}  {'band':<13}top drifting features")
    print("-" * 104)

    for label, window in windows[1:]:
        severity, per_feature = score(baseline, columnar(window, features))
        # Tie-break on PSI: severity saturates at 1.0, so ranking on it alone
        # orders saturated features arbitrarily and the printed PSI values
        # then look out of sequence.
        ranked = sorted(
            per_feature.items(),
            key=lambda kv: (kv[1]["severity"], kv[1]["psi"]),
            reverse=True,
        )
        top = "  ".join(f"{n} {s['psi']:.3f}" for n, s in ranked[: args.top])
        print(
            f"{label[:23]:<24}{len(window):>10,}{severity:>11.3f}  "
            f"{severity_band(severity):<13}{top}"
        )

    print(
        "\nseverity bands: <0.33 stable · 0.33-0.66 moderate · >0.66 significant"
        "\nPSI bands: <0.10 stable · 0.10-0.25 moderate shift · >0.25 significant shift"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
