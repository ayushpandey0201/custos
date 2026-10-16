"""Run the pre-registered gating study (PROTOCOL.md) on a Lending Club file.

    python -m experiments.gating.run data/accepted_2007_to_2018Q4.csv.gz \\
        --json experiments/results/lending_club_gating_v1.json

Pipeline: load a leakage-free, censoring-safe population → fit the credit model
and novelty scale on the training window → score population drift per window
with the same detector code the gateway runs → rank evaluation decisions under
every strategy → measure defaults caught per review at each budget → evaluate
the hypotheses mechanically, by the rules written before the data was seen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from engines.drift.severity import severity_band
from examples.datasets.replay import MIN_WINDOW, period_label
from examples.datasets.replay import score as drift_score
from experiments.gating import data as lc
from experiments.gating.model import LogisticRegression, Mahalanobis, Transform
from experiments.gating.stats import ECDF, auc, permutation_p, spearman, wilson
from experiments.gating.strategies import PROPOSED, STRATEGIES, Signals

PROTOCOL_VERSION = "gating-v1"
PRIMARY_BUDGET = 0.05
DEFAULT_BUDGETS = (0.01, 0.02, 0.05, 0.10, 0.20)
ROOT = Path(__file__).resolve().parents[2]


# --- helpers -----------------------------------------------------------------


def _month(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m")


def _columns(loans: Sequence[lc.Loan], features: Sequence[str]) -> dict[str, list[float]]:
    return {f: [loan.x[j] for loan in loans] for j, f in enumerate(features)}


def _windows(loans: Sequence[lc.Loan], period: str) -> list[tuple[str, list[int]]]:
    """Indices of loans grouped into calendar windows, in chronological order."""
    groups: dict[str, list[int]] = {}
    first: dict[str, datetime] = {}
    for i, loan in enumerate(loans):
        label = period_label(loan.issued, period)
        groups.setdefault(label, []).append(i)
        first[label] = min(first.get(label, loan.issued), loan.issued)
    return [(label, groups[label]) for label in sorted(groups, key=first.__getitem__)]


def _provenance(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)

    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {
        "dataset": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "run_at": datetime.now().isoformat(timespec="seconds"),
    }


# --- evaluation --------------------------------------------------------------


def evaluate(
    scores: Sequence[float],
    loans: Sequence[lc.Loan],
    budgets: Sequence[float],
    tie: Sequence[float],
) -> dict[str, dict]:
    """Review the top `budget` share by score; count the defaults among them."""
    n = len(loans)
    total_bad = sum(loan.bad for loan in loans)
    base = total_bad / n
    has_loss = all(loan.loss is not None for loan in loans)
    order = sorted(range(n), key=lambda i: (-scores[i], tie[i]))
    out: dict[str, dict] = {}
    for budget in budgets:
        k = max(1, round(budget * n))
        chosen = order[:k]
        caught = sum(loans[i].bad for i in chosen)
        lo, hi = wilson(caught, k)
        result = {
            "reviews": k,
            "defaults_caught": caught,
            "per_1000_reviews": round(1000 * caught / k, 2),
            "ci95_per_1000": [round(1000 * lo, 2), round(1000 * hi, 2)],
            "recall": round(caught / total_bad, 4) if total_bad else None,
            "lift": round((caught / k) / base, 3) if base else None,
            "principal_caught": round(sum(loans[i].principal for i in chosen if loans[i].bad), 2),
        }
        if has_loss:
            result["loss_caught"] = round(sum(loans[i].loss or 0.0 for i in chosen), 2)
        out[f"{budget:g}"] = result
    return out


def random_baseline(loans: Sequence[lc.Loan], budgets: Sequence[float]) -> dict[str, dict]:
    """Expected outcome of random review: precision is exactly the base rate."""
    n = len(loans)
    total_bad = sum(loan.bad for loan in loans)
    base = total_bad / n
    out: dict[str, dict] = {}
    for budget in budgets:
        k = max(1, round(budget * n))
        lo, hi = wilson(base * k, k)
        out[f"{budget:g}"] = {
            "reviews": k,
            "defaults_caught": round(base * k, 1),
            "per_1000_reviews": round(1000 * base, 2),
            "ci95_per_1000": [round(1000 * lo, 2), round(1000 * hi, 2)],
            "recall": round(budget, 4),
            "lift": 1.0,
            "principal_caught": None,
        }
    return out


def _compare(a: dict, b: dict) -> str:
    """'higher' / 'lower' if the 95% intervals separate, else 'overlap'."""
    if a["ci95_per_1000"][0] > b["ci95_per_1000"][1]:
        return "higher"
    if a["ci95_per_1000"][1] < b["ci95_per_1000"][0]:
        return "lower"
    return "overlap"


def hypotheses(results: dict[str, dict], drift_harm: dict, base_per_1000: float) -> list[dict]:
    """PROTOCOL.md's decision rules, applied mechanically."""
    key = f"{PRIMARY_BUDGET:g}"
    at = {name: r[key] for name, r in results.items()}
    verdicts: list[dict] = []

    pop = at["population_drift"]
    if pop["ci95_per_1000"][0] > base_per_1000:
        h1 = "supported"
    elif pop["ci95_per_1000"][1] < base_per_1000:
        h1 = "contradicted"
    else:
        h1 = "inconclusive"
    verdicts.append(
        {
            "id": "H1",
            "claim": "population-drift gating beats random review",
            "verdict": h1,
            "evidence": (
                f"{pop['per_1000_reviews']} {pop['ci95_per_1000']} vs base {base_per_1000:.2f}"
            ),
        }
    )

    for hid, claim, x, y in (
        ("H2", "per-request novelty beats population-drift gating", "novelty", "population_drift"),
        ("H3", f"{PROPOSED} beats model_risk", PROPOSED, "model_risk"),
    ):
        rel = _compare(at[x], at[y])
        verdict = {"higher": "supported", "lower": "contradicted"}.get(rel, "inconclusive")
        verdicts.append(
            {
                "id": hid,
                "claim": claim,
                "verdict": verdict,
                "evidence": (
                    f"{x} {at[x]['per_1000_reviews']} {at[x]['ci95_per_1000']} vs "
                    f"{y} {at[y]['per_1000_reviews']} {at[y]['ci95_per_1000']}"
                ),
            }
        )

    rho = drift_harm.get("rho_severity_calibration_gap")
    p = drift_harm.get("p_severity_calibration_gap")
    if rho is None or p is None:
        h4 = "inconclusive"
    elif rho > 0 and p < 0.05:
        h4 = "supported"
    elif rho < 0 and p < 0.05:
        h4 = "contradicted"
    else:
        h4 = "inconclusive"
    verdicts.append(
        {
            "id": "H4",
            "claim": "population drift predicts model error (calibration gap)",
            "verdict": h4,
            "evidence": (
                f"Spearman rho={rho} p={p} over {drift_harm.get('windows')} windows "
                f"(secondary, AUC: rho={drift_harm.get('rho_severity_auc')} "
                f"p={drift_harm.get('p_severity_auc')})"
            ),
        }
    )
    return verdicts


# --- the study ---------------------------------------------------------------


def run(args: argparse.Namespace) -> dict:
    t0 = time.perf_counter()

    def stage(text: str) -> None:
        print(f"[{time.perf_counter() - t0:6.1f}s] {text}", flush=True)

    features = tuple(f.strip() for f in args.features.split(",") if f.strip())
    stage(f"loading {args.csv.name}")
    study = lc.load(args.csv, features=features, term=args.term,
                    snapshot=_month(args.snapshot), progress=True)
    train_until, eval_until = _month(args.train_until), _month(args.eval_until)
    train = [loan for loan in study.loans if loan.issued <= train_until]
    test = [loan for loan in study.loans if train_until < loan.issued <= eval_until]
    if len(train) < MIN_WINDOW or len(test) < MIN_WINDOW:
        raise SystemExit(f"too few loans: train={len(train)}, eval={len(test)}")
    stage(f"kept {len(study.loans):,} of {study.rows_read:,} rows; "
          f"train {len(train):,}, eval {len(test):,}")

    # --- model and novelty scale, fit once on training data
    transform = Transform(features).fit([loan.x for loan in train])
    z_train = [transform(loan.x) for loan in train]
    z_test = [transform(loan.x) for loan in test]
    y_train = [loan.bad for loan in train]
    y_test = [loan.bad for loan in test]
    model = LogisticRegression(l2=1.0).fit(z_train, y_train)
    risk_train = [model.predict(z) for z in z_train]
    risk_test = [model.predict(z) for z in z_test]
    stage(f"model fit in {model.iterations} Newton steps")
    nov = Mahalanobis().fit(z_train)
    novelty_train = [nov(z) for z in z_train]
    novelty_test = [nov(z) for z in z_test]
    stage("novelty scale fit")

    # --- population drift per window, via the gateway's own detector code
    baseline = _columns(train, features)
    timeline = _windows(train + test, args.period)
    combined = train + test
    severities: list[float | None] = []
    window_rows: list[dict] = []
    first_eval = len(train)
    for label, idx in timeline:
        if idx[0] < first_eval <= idx[-1]:
            raise SystemExit(
                f"window {label} mixes training and evaluation loans; "
                f"--train-until must end a {args.period}"
            )
        members = [combined[i] for i in idx]
        if len(members) >= MIN_WINDOW:
            sev, per_feature = drift_score(baseline, _columns(members, features))
        else:
            sev, per_feature = None, {}
        severities.append(sev)
        is_eval = idx[0] >= first_eval
        if is_eval:
            labels = [combined[i].bad for i in idx]
            scores = [risk_test[i - first_eval] for i in idx]
            top = sorted(per_feature.items(), key=lambda kv: -kv[1]["psi"])[:2]
            actual, predicted = sum(labels) / len(labels), sum(scores) / len(scores)
            window_rows.append(
                {
                    "window": label,
                    "loans": len(idx),
                    "default_rate": round(actual, 4),
                    "mean_predicted": round(predicted, 4),
                    # How wrong the model's level is, in either direction.
                    "calibration_gap": round(abs(actual - predicted), 4),
                    "auc": None if (a := auc(scores, labels)) is None else round(a, 4),
                    "severity": None if sev is None else round(sev, 4),
                    "band": None if sev is None else severity_band(sev),
                    "top_drift": [f"{n} {s['psi']:.2f}" for n, s in top],
                }
            )
    stage(f"drift scored for {len(timeline)} windows")

    # Lagged severity: a decision may only use drift from windows already closed.
    lagged_by_window: list[float] = []
    for k in range(len(timeline)):
        known = [s for s in severities[: max(0, k - args.severity_lag + 1)] if s is not None]
        lagged_by_window.append(known[-1] if known else 0.0)
    severity_test = [0.0] * len(test)
    for k, (_, idx) in enumerate(timeline):
        for i in idx:
            if i >= first_eval:
                severity_test[i - first_eval] = lagged_by_window[k]

    # --- drift vs harm, across evaluation windows
    scored = [w for w in window_rows if w["severity"] is not None and w["auc"] is not None]
    sev_series = [w["severity"] for w in scored]
    gaps = [w["calibration_gap"] for w in scored]
    drift_harm = {
        "windows": len(scored),
        "rho_severity_calibration_gap": spearman(sev_series, gaps),
        "p_severity_calibration_gap": permutation_p(sev_series, gaps, seed=args.seed),
        "rho_severity_default_rate": spearman(sev_series, [w["default_rate"] for w in scored]),
        "p_severity_default_rate": permutation_p(
            sev_series, [w["default_rate"] for w in scored], seed=args.seed
        ),
        "rho_severity_auc": spearman(sev_series, [w["auc"] for w in scored]),
        "p_severity_auc": permutation_p(sev_series, [w["auc"] for w in scored], seed=args.seed),
    }
    drift_harm = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in drift_harm.items()}

    # --- strategies
    signals = Signals(
        risk=risk_test,
        novelty=novelty_test,
        severity=severity_test,
        risk_scale=ECDF(risk_train),
        novelty_scale=ECDF(novelty_train),
    )
    rng = random.Random(args.seed)
    tie = [rng.random() for _ in test]
    budgets = tuple(float(b) for b in args.budgets.split(","))
    results = {"random": random_baseline(test, budgets)}
    for name, strategy in STRATEGIES.items():
        results[name] = evaluate(strategy(signals), test, budgets, tie)
    stage("strategies evaluated")

    base = sum(y_test) / len(y_test)
    verdicts = hypotheses(results, drift_harm, 1000 * base)

    return {
        "protocol": PROTOCOL_VERSION,
        "provenance": _provenance(args.csv),
        "config": {
            "features": list(features),
            "term_months": args.term,
            "snapshot": args.snapshot,
            "train_until": args.train_until,
            "eval_until": args.eval_until,
            "period": args.period,
            "severity_lag": args.severity_lag,
            "budgets": list(budgets),
            "primary_budget": PRIMARY_BUDGET,
            "seed": args.seed,
        },
        "data": {
            "rows_read": study.rows_read,
            "kept": len(study.loans),
            "excluded": study.excluded,
            "train": {"loans": len(train), "default_rate": round(sum(y_train) / len(train), 4)},
            "eval": {"loans": len(test), "default_rate": round(base, 4)},
        },
        "model": {
            "weights": [round(w, 5) for w in model.weights],
            "train_auc": round(auc(risk_train, y_train) or 0.0, 4),
            "eval_auc": round(auc(risk_test, y_test) or 0.0, 4),
        },
        "windows": window_rows,
        "drift_vs_harm": drift_harm,
        "strategies": results,
        "hypotheses": verdicts,
    }


def report(result: dict) -> None:
    d, m = result["data"], result["model"]
    print(f"\n=== Gating study ({result['protocol']}) on {result['provenance']['dataset']}")
    print(f"rows read {d['rows_read']:,} · kept {d['kept']:,} · excluded {d['excluded']}")
    print(f"train {d['train']['loans']:,} loans, default rate {d['train']['default_rate']:.2%}")
    print(f"eval  {d['eval']['loans']:,} loans, default rate {d['eval']['default_rate']:.2%}")
    print(f"model AUC: train {m['train_auc']:.3f} · eval {m['eval_auc']:.3f}")

    print(f"\n{'window':<10}{'loans':>9}{'default':>9}{'predicted':>10}{'AUC':>8}{'drift':>8}"
          "  band          top drift")
    for w in result["windows"]:
        auc_s = "n/a" if w["auc"] is None else f"{w['auc']:.3f}"
        sev_s = "n/a" if w["severity"] is None else f"{w['severity']:.3f}"
        print(f"{w['window']:<10}{w['loans']:>9,}{w['default_rate']:>9.2%}"
              f"{w['mean_predicted']:>10.2%}{auc_s:>8}{sev_s:>8}"
              f"  {(w['band'] or '-'):<13} {', '.join(w['top_drift'])}")

    h = result["drift_vs_harm"]
    print(f"\ndrift vs harm over {h['windows']} windows (Spearman, permutation p):")
    print(f"  severity vs calibration gap  rho={h['rho_severity_calibration_gap']} "
          f"p={h['p_severity_calibration_gap']}   <- H4")
    print(f"  severity vs default rate     rho={h['rho_severity_default_rate']} "
          f"p={h['p_severity_default_rate']}")
    print(f"  severity vs AUC              rho={h['rho_severity_auc']} p={h['p_severity_auc']}")

    budgets = list(next(iter(result["strategies"].values())))
    print("\ndefaults caught per 1,000 reviews  [95% CI at the primary budget]")
    print(f"{'strategy':<20}" + "".join(f"{float(b):>9.0%}" for b in budgets) + "    lift @5%")
    primary = f"{PRIMARY_BUDGET:g}"
    for name, by_budget in result["strategies"].items():
        cells = "".join(f"{by_budget[b]['per_1000_reviews']:>9.1f}" for b in budgets)
        ci = by_budget[primary]["ci95_per_1000"]
        print(f"{name:<20}{cells}    {by_budget[primary]['lift']:.2f}  [{ci[0]:.0f}–{ci[1]:.0f}]")

    print("\npre-registered hypotheses (PROTOCOL.md):")
    for v in result["hypotheses"]:
        print(f"  {v['id']}  {v['verdict'].upper():<13} {v['claim']}")
        print(f"      {v['evidence']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--features", default=",".join(lc.ORIGINATION_FEATURES))
    parser.add_argument("--term", type=int, default=36)
    parser.add_argument("--snapshot", default="2018-12", help="data snapshot, YYYY-MM")
    parser.add_argument("--train-until", default="2011-12")
    parser.add_argument("--eval-until", default="2015-12")
    parser.add_argument("--period", choices=("month", "quarter", "year"), default="quarter")
    parser.add_argument("--severity-lag", type=int, default=1)
    parser.add_argument("--budgets", default=",".join(f"{b:g}" for b in DEFAULT_BUDGETS))
    parser.add_argument("--seed", type=int, default=20261016)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.csv.exists():
        parser.error(f"no such file: {args.csv}")
    result = run(args)
    report(result)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n")
        print(f"\nresults written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
