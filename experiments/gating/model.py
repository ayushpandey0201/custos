"""The credit model under study, and the per-request novelty score.

Pure standard library, like the rest of Custos: the whole study runs on any
machine with Python, and every piece of maths fits on a page. At Lending Club
scale (~10 features, tens of thousands of training rows) nothing here is slow
enough to justify a dependency.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# Heavy right tails; log1p brings them onto a scale a linear model can use.
LOG_FEATURES = frozenset({"annual_inc", "loan_amnt"})

Vector = list[float]
Matrix = list[list[float]]


# --- linear algebra ----------------------------------------------------------


def solve(a: Matrix, b: Vector) -> Vector:
    """Solve a·x = b by Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("matrix is singular")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            if factor:
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def inverse(a: Matrix) -> Matrix:
    n = len(a)
    columns = [solve(a, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[columns[j][i] for j in range(n)] for i in range(n)]


# --- feature transform -------------------------------------------------------


class Transform:
    """log1p on heavy-tailed features, then standardise with training statistics."""

    def __init__(self, features: Sequence[str]) -> None:
        self.features = tuple(features)
        self._log = [f in LOG_FEATURES for f in self.features]
        self.mean: Vector = []
        self.std: Vector = []

    def _raw(self, x: Sequence[float]) -> Vector:
        return [math.log1p(max(v, 0.0)) if lg else v for v, lg in zip(x, self._log, strict=True)]

    def fit(self, rows: Sequence[Sequence[float]]) -> Transform:
        logged = [self._raw(x) for x in rows]
        n, d = len(logged), len(self.features)
        if n < 2:
            raise ValueError("need at least two rows to fit a transform")
        self.mean = [sum(r[j] for r in logged) / n for j in range(d)]
        self.std = [
            math.sqrt(sum((r[j] - self.mean[j]) ** 2 for r in logged) / (n - 1)) or 1.0
            for j in range(d)
        ]
        return self

    def __call__(self, x: Sequence[float]) -> Vector:
        return [(v - m) / s for v, m, s in zip(self._raw(x), self.mean, self.std, strict=True)]


# --- logistic regression -----------------------------------------------------


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class LogisticRegression:
    """L2-regularised logistic regression, fit by Newton's method (IRLS).

    Newton rather than gradient descent: with ten features it converges in a
    handful of exact steps, with no learning rate to choose — one less knob
    that could be tuned after seeing results.
    """

    def __init__(self, l2: float = 1.0, max_iter: int = 30, tol: float = 1e-8) -> None:
        self.l2, self.max_iter, self.tol = l2, max_iter, tol
        self.weights: Vector = []  # [intercept, w1, ..., wd]
        self.iterations = 0

    def fit(self, rows: Sequence[Sequence[float]], labels: Sequence[int]) -> LogisticRegression:
        d = len(rows[0]) + 1
        w = [0.0] * d
        for iteration in range(1, self.max_iter + 1):
            hess = [[0.0] * d for _ in range(d)]
            grad = [0.0] * d
            for x, y in zip(rows, labels, strict=True):
                row = (1.0, *x)
                p = _sigmoid(sum(wi * xi for wi, xi in zip(w, row, strict=True)))
                residual, curvature = y - p, p * (1.0 - p)
                for a in range(d):
                    ra = row[a]
                    grad[a] += residual * ra
                    weighted = curvature * ra
                    h = hess[a]
                    for b in range(a, d):
                        h[b] += weighted * row[b]
            for a in range(d):
                for b in range(a):
                    hess[a][b] = hess[b][a]
            for a in range(1, d):  # the intercept is not penalised
                hess[a][a] += self.l2
                grad[a] -= self.l2 * w[a]
            step = solve(hess, grad)
            w = [wi + si for wi, si in zip(w, step, strict=True)]
            self.iterations = iteration
            if max(abs(s) for s in step) < self.tol:
                break
        self.weights = w
        return self

    def predict(self, x: Sequence[float]) -> float:
        return _sigmoid(
            self.weights[0] + sum(wi * xi for wi, xi in zip(self.weights[1:], x, strict=True))
        )


# --- novelty -----------------------------------------------------------------


class Mahalanobis:
    """How far one request sits from the training data, accounting for correlation.

    Univariate drift tests look at one feature at a time. Mahalanobis distance
    uses the full covariance, so an applicant whose income and loan amount are
    each ordinary but whose *combination* was never seen still scores as novel.
    """

    def __init__(self) -> None:
        self.mean: Vector = []
        self.precision: Matrix = []

    def fit(self, rows: Sequence[Sequence[float]]) -> Mahalanobis:
        n, d = len(rows), len(rows[0])
        self.mean = [sum(r[j] for r in rows) / n for j in range(d)]
        cov = [[0.0] * d for _ in range(d)]
        for r in rows:
            diff = [r[j] - self.mean[j] for j in range(d)]
            for a in range(d):
                da = diff[a]
                for b in range(a, d):
                    cov[a][b] += da * diff[b]
        for a in range(d):
            for b in range(a, d):
                cov[a][b] /= n - 1
                cov[b][a] = cov[a][b]
        # A tiny ridge keeps nearly-collinear features from making it singular.
        ridge = 1e-6 * sum(cov[i][i] for i in range(d)) / d
        for i in range(d):
            cov[i][i] += ridge
        self.precision = inverse(cov)
        return self

    def __call__(self, x: Sequence[float]) -> float:
        diff = [v - m for v, m in zip(x, self.mean, strict=True)]
        q = sum(
            diff[a] * sum(p * db for p, db in zip(self.precision[a], diff, strict=True))
            for a in range(len(diff))
        )
        return math.sqrt(max(q, 0.0))
