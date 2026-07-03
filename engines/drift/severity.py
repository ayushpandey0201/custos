"""Per-feature PSI/KS results -> one severity in [0, 1].

Monotonicity invariant: worse drift never yields a lower severity. See tests/unit/test_severity.py.
"""


def compute_severity(feature_results: dict[str, float]) -> float:
    raise NotImplementedError

