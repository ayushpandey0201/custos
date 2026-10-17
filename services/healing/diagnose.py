"""Tell a broken input feed apart from a real change in the population.

Drift statistics cannot do this on their own. A feed that dies and pins a
feature to a constant produces some of the largest PSI values there are, and so
does a genuine downturn — but they call for opposite responses. A real shift
may mean the model needs a new reference or retraining; a dead feed means the
model's input is garbage and *nothing* should be learned from it. The worst
thing a self-healing system can do is re-baseline on a broken feed, because it
teaches the drift alarm that broken data is the new normal. This module exists
so that never happens.

Pure functions over plain data, so every threshold here is unit-tested without
a database (tests/unit/test_diagnose.py).

Two pipeline-fault signatures, both from what practitioners report seeing most
(docs/conversations/01):

  missing  the input stopped arriving: absent, null, NaN or non-numeric in
           most of the recent window, though it was present in the baseline.
  stuck    the input arrives but no longer varies: one value accounts for
           almost all of the recent window, far more than it ever did in the
           baseline — the signature of a default-fill or a frozen upstream.

Anything else that moved a long way is treated as a population shift.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field

from engines.drift.severity import compute_severity, severity_band
from engines.drift.worker import score_features

# Missing: the input is absent from at least half of the recent window, and
# that is at least 30 points worse than it was in the baseline. The second
# condition keeps a feature that was always sparse from reading as broken.
MISSING_RATE = 0.5
MISSING_RISE = 0.3

# Stuck: one value covers at least 90% of the recent window, at least 30
# points more than that same value ever covered in the baseline. Relative,
# so a feature with a legitimate point mass (60% zeros) is only flagged when
# it collapses onto that value, not merely for having it.
STUCK_SHARE = 0.9
STUCK_RISE = 0.3

# Per-feature severity at which an input counts as having genuinely moved:
# the start of the "significant" band, matching the drift floor.
SHIFT_SEVERITY = 2 / 3

# Too few observations make every share above meaningless.
MIN_WINDOW = 30


@dataclass
class InputHealth:
    name: str
    # "ok" | "missing" | "stuck" | "shifted"
    status: str
    detail: str
    evidence: dict = field(default_factory=dict)


@dataclass
class Diagnosis:
    # "healthy" | "pipeline_break" | "population_shift" | "insufficient_data"
    kind: str
    summary: str
    window: int
    severity: float | None = None
    band: str | None = None
    inputs: list[InputHealth] = field(default_factory=list)

    @property
    def broken(self) -> list[InputHealth]:
        return [i for i in self.inputs if i.status in ("missing", "stuck")]

    @property
    def shifted(self) -> list[InputHealth]:
        return [i for i in self.inputs if i.status == "shifted"]

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "window": self.window,
            "severity": None if self.severity is None else round(self.severity, 4),
            "band": self.band,
            "inputs": [asdict(i) for i in self.inputs],
        }


def _numeric(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _top_share(values: list[float]) -> tuple[float, float]:
    """(most common value, the share of ``values`` it accounts for)."""
    value, count = Counter(values).most_common(1)[0]
    return value, count / len(values)


def inspect_input(
    name: str, reference: list[float], reference_rows: int, recent_rows: list[dict]
) -> InputHealth:
    """Classify one input over the recent window. Severity is filled in by the caller."""
    present = [v for v in (_numeric((row or {}).get(name)) for row in recent_rows) if v is not None]
    missing_rate = 1 - len(present) / len(recent_rows)
    reference_missing = 1 - len(reference) / reference_rows if reference_rows else 0.0

    if missing_rate >= MISSING_RATE and missing_rate - reference_missing >= MISSING_RISE:
        return InputHealth(
            name,
            "missing",
            f"missing from {missing_rate:.0%} of recent requests "
            f"(baseline: {reference_missing:.0%})",
            {
                "missing_rate": round(missing_rate, 4),
                "baseline_missing_rate": round(reference_missing, 4),
            },
        )

    if len(present) >= MIN_WINDOW and reference:
        value, share = _top_share(present)
        reference_share = sum(1 for v in reference if v == value) / len(reference)
        if share >= STUCK_SHARE and share - reference_share >= STUCK_RISE:
            return InputHealth(
                name,
                "stuck",
                f"stuck at {value:g} in {share:.0%} of recent requests "
                f"(baseline: {reference_share:.0%})",
                {
                    "value": value,
                    "share": round(share, 4),
                    "baseline_share": round(reference_share, 4),
                },
            )

    return InputHealth(name, "ok", "", {"missing_rate": round(missing_rate, 4)})


def diagnose(baseline: dict[str, list[float]], recent_rows: list[dict]) -> Diagnosis:
    """Diagnose a model's recent traffic against its baseline.

    Pipeline faults take precedence over shift: if any input is broken, the
    incident is a pipeline break, even if other inputs have also moved —
    those are reported alongside, but nothing should be re-learned while part
    of the input is garbage.
    """
    window = len(recent_rows)
    if window < MIN_WINDOW or not baseline:
        return Diagnosis(
            "insufficient_data",
            f"{window} recent requests; at least {MIN_WINDOW} are needed to diagnose",
            window,
        )

    reference_rows = max(len(v) for v in baseline.values())
    inputs = [
        inspect_input(name, reference, reference_rows, recent_rows)
        for name, reference in sorted(baseline.items())
    ]

    # Drift on the same window, so the severity quoted matches what was inspected.
    live: dict[str, list[float]] = {}
    for row in recent_rows:
        for name, value in (row or {}).items():
            number = _numeric(value)
            if number is not None:
                live.setdefault(name, []).append(number)
    per_feature = score_features(baseline, live)
    for health in inputs:
        stats = per_feature.get(health.name)
        if stats is None:
            continue
        health.evidence["severity"] = stats["severity"]
        health.evidence["psi"] = stats["psi"]
        if health.status == "ok" and stats["severity"] >= SHIFT_SEVERITY:
            health.status = "shifted"
            health.detail = f"distribution moved (PSI {stats['psi']:.2f})"

    severity = (
        compute_severity({n: s["severity"] for n, s in per_feature.items()})
        if per_feature
        else None
    )
    band = None if severity is None else severity_band(severity)
    diagnosis = Diagnosis("healthy", "", window, severity, band, inputs)

    if diagnosis.broken:
        names = ", ".join(i.name for i in diagnosis.broken)
        diagnosis.kind = "pipeline_break"
        diagnosis.summary = (
            f"Upstream feed broken: {names}. The population did not change; the data did."
        )
    elif band == "significant":
        names = ", ".join(i.name for i in diagnosis.shifted) or "several inputs"
        diagnosis.kind = "population_shift"
        diagnosis.summary = (
            f"The population has shifted ({names}); every input is still arriving normally."
        )
    else:
        diagnosis.summary = "All inputs arriving and within their expected range."
    return diagnosis
