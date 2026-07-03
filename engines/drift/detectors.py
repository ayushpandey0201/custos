"""psi() and ks_test() — pure functions, heavily unit-tested."""

import numpy as np


def psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    raise NotImplementedError


def ks_test(expected: np.ndarray, actual: np.ndarray) -> float:
    raise NotImplementedError

