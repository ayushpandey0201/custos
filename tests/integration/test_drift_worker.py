"""Ingest batch -> worker -> severity persisted + cached."""

from __future__ import annotations

from datetime import UTC

import pytest
from sqlalchemy import select

from engines.drift import engine as drift_engine
from engines.drift import worker
from shared.db.models import DriftSnapshot, FeatureSample, Model
from shared.db.session import session_scope
from tests.conftest import normal_sample, rows_from_columns


def register(tenant: str, model_id: str = "credit-risk-v3") -> str:
    with session_scope() as db:
        db.add(Model(tenant_id=tenant, model_id=model_id, name=model_id))
    return model_id


def ingest(tenant: str, model_id: str, rows: list[dict]) -> None:
    with session_scope() as db:
        for row in rows:
            db.add(FeatureSample(tenant_id=tenant, model_id=model_id, features=row))


def shifted(rows: list[dict], shift: dict[str, float]) -> list[dict]:
    return [{k: v + shift.get(k, 0.0) for k, v in row.items()} for row in rows]


class TestBuildBaseline:
    def test_baseline_is_persisted_columnwise(self, tenant, baseline_features):
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)

        baseline = worker.build_baseline(tenant, model_id, samples=rows)

        assert set(baseline) == {"income", "utilisation", "age"}
        with session_scope() as db:
            model = db.execute(select(Model).where(Model.model_id == model_id)).scalar_one()
            assert set(model.baseline) == set(baseline)
            assert model.baseline_at is not None

    def test_baseline_can_be_built_from_ingested_samples(self, tenant, baseline_features):
        model_id = register(tenant)
        ingest(tenant, model_id, rows_from_columns(baseline_features))

        baseline = worker.build_baseline(tenant, model_id)
        assert len(baseline["income"]) == 500

    def test_unregistered_model_is_rejected(self, tenant):
        with pytest.raises(LookupError):
            worker.build_baseline(tenant, "ghost-model", samples=[{"a": 1.0}])

    def test_no_samples_is_rejected(self, tenant):
        model_id = register(tenant)
        with pytest.raises(ValueError):
            worker.build_baseline(tenant, model_id)

    def test_non_numeric_features_are_dropped(self, tenant):
        model_id = register(tenant)
        baseline = worker.build_baseline(
            tenant,
            model_id,
            samples=[{"income": 1.0, "region": "IN", "verified": True} for _ in range(10)],
        )
        # Strings and booleans are not distributions PSI can speak about.
        assert set(baseline) == {"income"}


class TestRecomputeDrift:
    def test_stable_window_yields_low_severity(self, tenant, baseline_features):
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)
        ingest(tenant, model_id, rows)

        result = worker.recompute_drift(tenant, model_id)

        assert result is not None
        assert result["severity"] < 1 / 3
        assert result["sample_size"] == 500

    def test_shifted_window_yields_high_severity(self, tenant, baseline_features):
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)
        ingest(tenant, model_id, shifted(rows, {"income": 40000}))

        result = worker.recompute_drift(tenant, model_id)
        assert result["severity"] > 1 / 3
        assert result["per_feature"]["income"]["psi"] > 0.25

    def test_snapshot_is_persisted(self, tenant, baseline_features):
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)
        ingest(tenant, model_id, rows)
        worker.recompute_drift(tenant, model_id)

        with session_scope() as db:
            snapshots = list(db.execute(select(DriftSnapshot)).scalars())
        assert len(snapshots) == 1
        assert set(snapshots[0].per_feature) == {"income", "utilisation", "age"}

    def test_every_feature_gets_psi_ks_and_severity(self, tenant, baseline_features):
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)
        ingest(tenant, model_id, rows)

        result = worker.recompute_drift(tenant, model_id)
        for stats in result["per_feature"].values():
            assert {"psi", "ks", "severity"} <= set(stats)

    def test_no_baseline_returns_none(self, tenant, baseline_features):
        model_id = register(tenant)
        ingest(tenant, model_id, rows_from_columns(baseline_features))
        assert worker.recompute_drift(tenant, model_id) is None

    def test_too_few_samples_returns_none(self, tenant, baseline_features):
        """A PSI over a handful of rows is noise, not a signal."""
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)
        ingest(tenant, model_id, rows[: worker.MIN_SAMPLES - 1])

        assert worker.recompute_drift(tenant, model_id) is None

    def test_window_excludes_older_samples(self, tenant, baseline_features):
        """Only traffic inside the window is scored."""
        from datetime import datetime, timedelta

        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)

        stale = datetime.now(UTC) - timedelta(days=30)
        with session_scope() as db:
            for row in rows:
                db.add(
                    FeatureSample(
                        tenant_id=tenant, model_id=model_id, features=row, created_at=stale
                    )
                )

        assert worker.recompute_drift(tenant, model_id, window_hours=24) is None

    def test_recompute_invalidates_the_hot_path_cache(self, tenant, baseline_features):
        """A new snapshot must be visible immediately, not after the TTL."""
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)

        # Warm the cache with the "no snapshot yet" miss.
        assert drift_engine.latest_snapshot(tenant, model_id) is None

        ingest(tenant, model_id, shifted(rows, {"income": 40000}))
        worker.recompute_drift(tenant, model_id)

        snapshot = drift_engine.latest_snapshot(tenant, model_id)
        assert snapshot is not None
        assert snapshot["severity"] > 1 / 3

    def test_latest_snapshot_wins(self, tenant, baseline_features):
        model_id = register(tenant)
        rows = rows_from_columns(baseline_features)
        worker.build_baseline(tenant, model_id, samples=rows)

        ingest(tenant, model_id, rows)
        first = worker.recompute_drift(tenant, model_id)

        ingest(tenant, model_id, shifted(rows, {"income": 40000}))
        second = worker.recompute_drift(tenant, model_id)

        assert second["severity"] > first["severity"]
        assert drift_engine.latest_snapshot(tenant, model_id)["severity"] == pytest.approx(
            second["severity"]
        )


class TestPipelineHealth:
    def test_a_feature_that_vanished_is_reported_separately(self, tenant, rng):
        """A missing feature is a pipeline failure, not distribution drift.

        The two demand different responses — fix the pipeline vs. investigate
        the population — so they must not be collapsed into one number.
        """
        baseline = {
            "income": normal_sample(rng, 60000, 15000, 100),
            "bureau_score": normal_sample(rng, 700, 50, 100),
        }
        live = {"income": normal_sample(rng, 60000, 15000, 100)}

        assert worker.missing_features(baseline, live) == ["bureau_score"]

    def test_present_features_report_nothing_missing(self, tenant, baseline_features):
        assert worker.missing_features(baseline_features, baseline_features) == []

    def test_severity_ignores_features_absent_from_live_traffic(self, tenant, rng):
        model_id = register(tenant)
        rows = [
            {"income": v, "bureau_score": s}
            for v, s in zip(
                normal_sample(rng, 60000, 15000, 200),
                normal_sample(rng, 700, 50, 200),
                strict=True,
            )
        ]
        worker.build_baseline(tenant, model_id, samples=rows)
        ingest(tenant, model_id, [{"income": r["income"]} for r in rows])

        result = worker.recompute_drift(tenant, model_id)
        assert set(result["per_feature"]) == {"income"}
