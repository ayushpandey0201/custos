"""The gating-study harness: data rules, maths, and recovery of a planted answer.

The harness produces the numbers a paper would rest on, so it is held to the
standard the drift detector is: every rule that could silently corrupt a result
(leakage, censoring, window mixing) is tested, and the end-to-end run must
recover what synthetic.py planted.
"""

from __future__ import annotations

import gzip
import json
import math
import random

import pytest

from experiments.gating import data as lc
from experiments.gating.model import LogisticRegression, Mahalanobis, Transform, inverse, solve
from experiments.gating.run import evaluate, main, random_baseline
from experiments.gating.stats import ECDF, auc, average_ranks, permutation_p, spearman, wilson
from experiments.gating.synthetic import generate

# --- data rules --------------------------------------------------------------


class TestLeakageGuard:
    def test_post_origination_columns_are_refused(self):
        with pytest.raises(ValueError, match="leak"):
            lc.check_features(("annual_inc", "total_pymnt"))

    def test_duplicates_are_refused(self):
        with pytest.raises(ValueError, match="duplicate"):
            lc.check_features(("dti", "dti"))

    def test_the_allowlist_itself_passes(self):
        lc.check_features(lc.ORIGINATION_FEATURES)


def _write(path, rows, notes_line=False):
    header = ["issue_d", "term", "loan_status", "loan_amnt", "annual_inc", "dti",
              "funded_amnt", "total_rec_prncp", "recoveries"]
    with gzip.open(path, "wt", newline="") as fh:
        if notes_line:
            fh.write('"Notes offered by Prospectus"\n')
        fh.write(",".join(header) + "\n")
        for r in rows:
            fh.write(",".join(str(v) for v in r) + "\n")


class TestLoading:
    FEATURES = ("loan_amnt", "annual_inc", "dti")

    def test_every_exclusion_rule_and_label(self, tmp_path):
        path = tmp_path / "lc.csv.gz"
        _write(
            path,
            [
                ["Jan-2012", " 36 months", "Fully Paid", 1000, 50000, "10%", 1000, 1000, 0],
                ["Feb-2012", " 36 months", "Charged Off", 2000, 40000, 20, 2000, 500, 100],
                ["Mar-2012", " 60 months", "Fully Paid", 1000, 50000, 10, 1000, 1000, 0],
                ["Jun-2016", " 36 months", "Fully Paid", 1000, 50000, 10, 1000, 1000, 0],
                ["Apr-2012", " 36 months", "Current", 1000, 50000, 10, 1000, 1000, 0],
                ["May-2012", " 36 months", "Fully Paid", 1000, "", 10, 1000, 1000, 0],
                ["not a date", " 36 months", "Fully Paid", 1000, 50000, 10, 1000, 1000, 0],
            ],
            notes_line=True,
        )
        study = lc.load(path, features=self.FEATURES)
        assert study.excluded == {
            "unparseable_date": 1,
            "other_term": 1,
            "not_matured": 1,  # 2016 + 36 months runs past the 2018-12 snapshot
            "unresolved_status": 1,
            "missing_feature": 1,
        }
        assert [loan.bad for loan in study.loans] == [0, 1]
        assert study.loans[0].x == (1000.0, 50000.0, 10.0)  # "10%" parsed
        assert study.loans[1].loss == pytest.approx(1400.0)  # 2000 - 500 - 100
        assert study.loans[0].loss == 0.0

    def test_maturity_boundary_is_inclusive(self, tmp_path):
        path = tmp_path / "lc.csv.gz"
        _write(path, [["Dec-2015", " 36 months", "Fully Paid", 1, 1, 1, 1, 1, 0],
                      ["Jan-2016", " 36 months", "Fully Paid", 1, 1, 1, 1, 1, 0]])
        study = lc.load(path, features=self.FEATURES)
        assert len(study.loans) == 1 and study.excluded["not_matured"] == 1


# --- maths -------------------------------------------------------------------


class TestLinearAlgebra:
    def test_solve(self):
        assert solve([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0]) == pytest.approx([0.8, 1.4])

    def test_inverse(self):
        a = [[4.0, 2.0, 0.6], [2.0, 2.0, 0.4], [0.6, 0.4, 0.25]]
        inv = inverse(a)
        for i in range(3):
            for j in range(3):
                assert sum(a[i][k] * inv[k][j] for k in range(3)) == pytest.approx(
                    1.0 if i == j else 0.0, abs=1e-9
                )

    def test_singular_is_refused(self):
        with pytest.raises(ValueError):
            solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])


class TestModels:
    def test_logistic_regression_recovers_the_planted_coefficient(self):
        rng = random.Random(1)
        rows, labels = [], []
        for _ in range(4000):
            x = rng.gauss(0, 1)
            rows.append([x])
            labels.append(int(rng.random() < 1 / (1 + math.exp(-(-1.0 + 2.0 * x)))))
        model = LogisticRegression(l2=0.0).fit(rows, labels)
        assert model.weights[0] == pytest.approx(-1.0, abs=0.15)
        assert model.weights[1] == pytest.approx(2.0, abs=0.2)

    def test_transform_standardises_training_data(self):
        t = Transform(("dti", "annual_inc")).fit([[10, 30000], [20, 60000], [30, 90000]])
        z = [t(x) for x in ([10, 30000], [20, 60000], [30, 90000])]
        for j in range(2):
            col = [r[j] for r in z]
            assert sum(col) == pytest.approx(0.0, abs=1e-9)
            assert math.sqrt(sum(v * v for v in col) / 2) == pytest.approx(1.0)

    def test_mahalanobis_reduces_to_euclidean_for_independent_unit_data(self):
        rng = random.Random(2)
        rows = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(20000)]
        distance = Mahalanobis().fit(rows)
        assert distance([3.0, 4.0]) == pytest.approx(5.0, rel=0.03)

    def test_mahalanobis_sees_an_unusual_combination(self):
        """Each coordinate ordinary; together, never seen. Univariate tests miss this."""
        rng = random.Random(3)
        rows = []
        for _ in range(20000):
            a = rng.gauss(0, 1)
            rows.append([a, a + rng.gauss(0, 0.1)])  # strongly correlated
        distance = Mahalanobis().fit(rows)
        assert distance([1.0, -1.0]) > 5 * distance([1.0, 1.0])


class TestStatistics:
    def test_ranks_share_ties(self):
        assert average_ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]

    def test_auc(self):
        assert auc([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0
        assert auc([4, 3, 2, 1], [0, 0, 1, 1]) == 0.0
        assert auc([1, 1, 1, 1], [0, 0, 1, 1]) == 0.5
        assert auc([1, 2], [1, 1]) is None

    def test_spearman(self):
        assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
        assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
        assert spearman([1, 2, 3, 4], [5, 5, 5, 5]) is None

    def test_permutation_p(self):
        assert permutation_p(list(range(10)), list(range(10)), n_perm=2000) < 0.01
        rng = random.Random(4)
        noise = [rng.random() for _ in range(10)]
        assert permutation_p(list(range(10)), noise, n_perm=2000) > 0.05

    def test_wilson(self):
        lo, hi = wilson(50, 100)
        assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)

    def test_ecdf(self):
        scale = ECDF([1, 2, 3, 4])
        assert (scale(0), scale(2), scale(9)) == (0.0, 0.5, 1.0)


class TestEvaluation:
    def _loans(self, bads):
        return [lc.Loan(issued=None, x=(), bad=b, principal=100.0, loss=None) for b in bads]

    def test_reviews_the_highest_scores(self):
        loans = self._loans([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
        out = evaluate([9, 1, 8, 2, 3, 4, 5, 6, 7, 0], loans, [0.2], tie=[0.0] * 10)
        assert out["0.2"]["defaults_caught"] == 2
        assert out["0.2"]["per_1000_reviews"] == 1000.0
        assert out["0.2"]["recall"] == 1.0

    def test_ties_are_broken_by_the_tie_key_not_input_order(self):
        loans = self._loans([0, 1])
        out = evaluate([1, 1], loans, [0.5], tie=[0.9, 0.1])
        assert out["0.5"]["defaults_caught"] == 1

    def test_random_review_catches_at_the_base_rate(self):
        loans = self._loans([1] * 3 + [0] * 7)
        out = random_baseline(loans, [0.2])
        assert out["0.2"]["per_1000_reviews"] == 300.0 and out["0.2"]["lift"] == 1.0


# --- end to end: the harness must find what was planted -----------------------


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    folder = tmp_path_factory.mktemp("gating")
    path = folder / "synthetic.csv.gz"
    generate(path, per_month=100)
    out = folder / "result.json"
    assert main([str(path), "--json", str(out)]) == 0
    return path, json.loads(out.read_text())


class TestPlantedAnswer:
    def test_every_exclusion_rule_fired(self, planted):
        _, r = planted
        for rule in ("other_term", "not_matured", "unresolved_status"):
            assert r["data"]["excluded"][rule] > 0, rule

    def test_drift_appears_where_it_was_planted(self, planted):
        _, r = planted
        sev = {w["window"]: w["severity"] for w in r["windows"]}
        before = [v for k, v in sev.items() if k.startswith("2012")]
        after = [v for k, v in sev.items() if k >= "2013"]
        assert min(after) > max(before)

    def test_novelty_finds_the_segment_the_model_never_saw(self, planted):
        _, r = planted
        assert r["strategies"]["novelty"]["0.05"]["lift"] > 1.3

    def test_population_drift_cannot_rank_inside_a_drifted_period(self, planted):
        """The pilot finding: when drift persists, periods stop discriminating."""
        _, r = planted
        s = r["strategies"]
        assert s["population_drift"]["0.05"]["lift"] < s["novelty"]["0.05"]["lift"]

    def test_random_is_exactly_the_base_rate(self, planted):
        _, r = planted
        base = r["data"]["eval"]["default_rate"]
        assert r["strategies"]["random"]["0.05"]["per_1000_reviews"] == pytest.approx(
            1000 * base, abs=0.1
        )

    def test_model_risk_beats_random(self, planted):
        _, r = planted
        assert r["strategies"]["model_risk"]["0.05"]["lift"] > 1.1

    def test_planted_drift_shows_up_as_model_error(self, planted):
        _, r = planted
        assert next(h for h in r["hypotheses"] if h["id"] == "H4")["verdict"] == "supported"

    def test_hypotheses_are_all_evaluated(self, planted):
        _, r = planted
        assert [h["id"] for h in r["hypotheses"]] == ["H1", "H2", "H3", "H4"]
        assert {h["verdict"] for h in r["hypotheses"]} <= {
            "supported", "contradicted", "inconclusive"
        }

    def test_provenance_pins_the_exact_input(self, planted):
        _, r = planted
        assert len(r["provenance"]["sha256"]) == 64

    def test_deterministic(self, planted, tmp_path):
        path, first = planted
        out = tmp_path / "again.json"
        main([str(path), "--json", str(out)])
        assert json.loads(out.read_text())["strategies"] == first["strategies"]

    def test_a_split_inside_a_window_is_refused(self, planted):
        path, _ = planted
        with pytest.raises(SystemExit, match="mixes training and evaluation"):
            main([str(path), "--train-until", "2011-11"])
