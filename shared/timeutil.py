"""UTC time helpers.

Everything Custos stores is UTC. The problem is that some backends give it back
without saying so: SQLite has no native timestamp type, so a ``DateTime`` round
-trips as a *naive* datetime. Calling ``.isoformat()`` on that produces a string
with no offset, and any ISO-8601 consumer — including every browser — is then
entitled to read it as local time.

That is not a cosmetic issue. It silently shifts every timestamp in the
dashboard by the operator's UTC offset, which in an audit tool is the kind of
wrong that gets noticed at exactly the wrong moment.

So: one function that serialises datetimes, used everywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware current time. The only way this codebase makes a 'now'."""
    return datetime.now(UTC)


def iso_utc(value: datetime | None) -> str | None:
    """Serialise a datetime as an unambiguous UTC ISO-8601 string.

    A naive value is *assumed* to be UTC — which is true here because every
    write goes through :func:`utcnow` — and tagged as such. An aware value is
    converted. ``None`` passes through so callers can serialise nullable
    columns without a branch at each site.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
