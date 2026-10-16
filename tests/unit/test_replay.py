"""The real-data replay harness: ordering, windowing, and finding a planted shift.

The harness is the instrument behind the "field" half of validation. If it
mis-orders windows, every number it prints is meaningless while still looking
plausible — which is exactly how the original string-sort bug went unnoticed.
"""

from __future__ import annotations

import csv
import gzip
import json
import random

from examples.datasets.replay import main, parse_time, window_by_time


def _rows(labels: list[str]) -> list[dict]:
    return [{"__t": label} for label in labels]


class TestChronologicalOrdering:
    def test_lending_club_month_format_sorts_by_date_not_alphabet(self):
        """The regression: "Aug-2018" sorted before "Jun-2007" as plain text."""
        rows = _rows(["Jun-2007", "Dec-2008", "Jan-2016", "Mar-2012", "Aug-2018", "Feb-2010"])
        order = [label for label, _ in window_by_time(rows, "month")]
        assert order == ["2007-06", "2008-12", "2010-02", "2012-03", "2016-01", "2018-08"]

    def test_quarter_windows_merge_months_in_order(self):
        rows = _rows(["Jan-2008", "Mar-2008", "Apr-2008", "Dec-2007"])
        windows = window_by_time(rows, "quarter")
        assert [label for label, _ in windows] == ["2007-Q4", "2008-Q1", "2008-Q2"]
        assert [len(w) for _, w in windows] == [1, 2, 1]

    def test_year_windows(self):
        rows = _rows(["Dec-2009", "Jan-2008", "Jun-2009"])
        assert [label for label, _ in window_by_time(rows, "year")] == ["2008", "2009"]

    def test_iso_dates_are_understood(self):
        assert parse_time("2016-03-01").year == 2016
        assert parse_time("Dec-2015").month == 12

    def test_unparseable_times_are_dropped_not_guessed(self):
        windows = window_by_time(_rows(["Jan-2010", "not a date", ""]), "month")
        assert [label for label, _ in windows] == ["2010-01"]


class TestEndToEnd:
    def test_finds_a_planted_shift_at_the_right_time(self, tmp_path):
        """Calibrate the harness itself: plant a shift in 2016, read it back.

        A .gz in Lending Club's own format, stable through 2015, with incomes
        dropping sharply from 2016. Pre-shift windows must read lower severity
        than post-shift ones, and the shifted feature must be the one blamed.
        """
        rng = random.Random(20261016)
        path = tmp_path / "loans.csv.gz"
        months = ["Jan", "Apr", "Jul", "Oct"]
        with gzip.open(path, "wt", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["issue_d", "annual_inc", "dti", "revol_util"])
            for year in range(2013, 2018):
                for month in months:
                    shift = 25000 if year >= 2016 else 0
                    for _ in range(300):
                        writer.writerow(
                            [
                                f"{month}-{year}",
                                f"{rng.gauss(70000 - shift, 15000):.0f}",
                                f"{rng.gauss(18, 6):.2f}",
                                f"{rng.gauss(50, 15):.1f}%",
                            ]
                        )

        out = tmp_path / "timeline.json"
        code = main(
            [
                str(path),
                "--time-column", "issue_d",
                "--period", "quarter",
                "--features", "annual_inc,dti,revol_util",
                "--json", str(out),
            ]
        )
        assert code == 0

        result = json.loads(out.read_text())
        assert result["baseline"]["window"] == "2013-Q1"
        timeline = {w["window"]: w for w in result["timeline"]}

        before = max(w["severity"] for k, w in timeline.items() if k < "2016")
        after = min(w["severity"] for k, w in timeline.items() if k >= "2016")
        assert after > before, "planted 2016 shift not separated from stable windows"

        top = max(
            timeline["2016-Q1"]["per_feature"].items(), key=lambda kv: kv[1]["psi"]
        )[0]
        assert top == "annual_inc", "the shifted feature should be the one blamed"
