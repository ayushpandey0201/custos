"""Shared fixtures: test DB, mock tenant config, sample data.

Every test gets its own SQLite file and a cleared cache. Sharing either between
tests makes ordering load-bearing, and a suite whose result depends on test
order stops being evidence of anything.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

# The SDK lives outside the importable package root; add it so tests can
# exercise the same import path a real integrator uses.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

from engines import registry  # noqa: E402
from services.gateway.auth import hash_api_key  # noqa: E402
from shared.cache import reset_cache  # noqa: E402
from shared.config.tenant import TenantConfig  # noqa: E402
from shared.db import session as db_session  # noqa: E402
from shared.db.models import Base, PolicyRule, Tenant  # noqa: E402
from shared.telemetry import metrics  # noqa: E402

TEST_TENANT = "acme"
TEST_API_KEY = "test_key_abc123"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Fresh database + cache + metrics for every test."""
    db_file = tmp_path / "test.db"
    engine = db_session.init_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    reset_cache()
    metrics.reset()
    registry.load_builtin_engines()

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()
    reset_cache()


@pytest.fixture
def tenant():
    """A tenant with default config and a known API key."""
    config = TenantConfig.default(TEST_TENANT).model_dump()
    config.pop("tenant_id")
    with db_session.session_scope() as db:
        db.add(
            Tenant(
                tenant_id=TEST_TENANT,
                name="Acme Lending",
                api_key_hash=hash_api_key(TEST_API_KEY),
                config=config,
            )
        )
    return TEST_TENANT


@pytest.fixture
def registered_model(tenant):
    """A registered model with no baseline yet."""
    from shared.db.models import Model

    with db_session.session_scope() as db:
        db.add(Model(tenant_id=tenant, model_id="credit-risk-v3", name="Credit Risk"))
    return "credit-risk-v3"


@pytest.fixture
def veto_rule(tenant):
    """A rule that hard-blocks disbursements above 500k."""
    with db_session.session_scope() as db:
        db.add(
            PolicyRule(
                tenant_id=tenant,
                rule_id="max-disbursement",
                condition='action == "disburse" and amount > 500000',
                action="veto",
                description="disbursements above 500000 require manual authorisation",
            )
        )
    return "max-disbursement"


@pytest.fixture
def rng():
    """Seeded RNG. Statistical tests must not be able to fail intermittently."""
    return random.Random(20260904)


def normal_sample(rng: random.Random, mu: float, sigma: float, n: int) -> list[float]:
    return [rng.gauss(mu, sigma) for _ in range(n)]


@pytest.fixture
def baseline_features(rng):
    """A three-feature reference distribution resembling credit-risk inputs."""
    return {
        "income": normal_sample(rng, 60000, 15000, 500),
        "utilisation": normal_sample(rng, 0.35, 0.12, 500),
        "age": normal_sample(rng, 38, 9, 500),
    }


def rows_from_columns(columns: dict[str, list[float]]) -> list[dict[str, float]]:
    """Column-oriented fixtures -> the row-oriented shape the API accepts."""
    length = min(len(v) for v in columns.values())
    return [{name: values[i] for name, values in columns.items()} for i in range(length)]
