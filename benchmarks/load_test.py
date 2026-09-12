"""Concurrency load test for the gateway hot path — does the 50 ms p99 budget hold?

    python -m benchmarks.load_test                    # sweep, find the ceiling
    python -m benchmarks.load_test --rps 200 --duration 30
    python -m benchmarks.load_test --database-url postgresql+psycopg://...

G2 in ``docs/architecture.md`` claims a sub-50 ms p99 on ``POST /v1/evaluate``.
Until this file existed, the evidence for that was a single-threaded demo run,
which measures the one thing a latency budget is *not* about: an idle server
answering one caller. This drives the real gateway over real HTTP at a
controlled request rate and reports what a client actually experiences.

Three decisions here are methodological rather than incidental, and each one
exists because the obvious alternative produces a flattering wrong answer.

**The generator is open-loop.** The obvious load generator keeps N workers in a
send-wait-send loop. That is closed-loop, and it silently corrects for the
thing being measured: when the server slows down, the generator sends *less*
traffic, so the slow period is under-sampled and p99 comes out far too good.
This is Gil Tene's coordinated-omission problem. Here every request has a
scheduled send time fixed before the run starts, and latency is measured from
that scheduled time — so a request that could not be sent on time carries the
delay it actually suffered. Both numbers are reported:

    service time    actual send -> response.  What the server took.
    response time   scheduled   -> response.  What the caller waited.

They are equal while there is headroom and diverge sharply at saturation. The
gap *is* the queueing delay, and reporting only the first is how a saturated
system gets published as a fast one.

**Server and generator are separate processes.** Running uvicorn in a thread
next to the load generator is simpler and wrong: they contend for one GIL, so
the generator's own CPU time lands inside the measured latency.

**The measurement does not use the system's own instrument.** Percentiles here
are computed from raw client-side samples rather than through
``shared.telemetry.metrics``. A bug in the ring buffer or the rank arithmetic
would otherwise be invisible to the test that is supposed to catch it.

Warmup traffic is discarded: the first requests pay for lazy imports, an empty
API-key cache, and an empty drift cache. Those costs are real but they are
start-up costs, not steady-state latency, and averaging them in describes
neither.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, YELLOW, RED, CYAN = "\033[32m", "\033[33m", "\033[31m", "\033[36m"

MODEL_ID = "credit-risk-v3"
TENANT_ID = "bench"

# Rates for --sweep. Geometric, so the ceiling is bracketed in few steps
# whether it turns out to be 50 req/s or 2000.
DEFAULT_SWEEP = [25, 50, 100, 200, 400, 800]


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------


def percentile(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile: rank = ceil(p/100 * n).

    ``ceil`` rather than ``round`` for the same reason as in
    ``shared.telemetry.metrics``: Python's ``round`` is banker's rounding, so a
    half-way rank alternates between neighbours depending on parity.
    """
    if not sorted_values:
        return float("nan")
    rank = math.ceil(max(0.0, min(100.0, p)) / 100.0 * len(sorted_values))
    return sorted_values[min(len(sorted_values) - 1, max(rank - 1, 0))]


@dataclass(frozen=True)
class Distribution:
    """Percentiles over one latency series."""

    p50: float
    p95: float
    p99: float
    max: float
    mean: float
    count: int

    @classmethod
    def of(cls, values: list[float]) -> Distribution:
        if not values:
            nan = float("nan")
            return cls(nan, nan, nan, nan, nan, 0)
        ordered = sorted(values)
        return cls(
            p50=percentile(ordered, 50),
            p95=percentile(ordered, 95),
            p99=percentile(ordered, 99),
            max=ordered[-1],
            mean=sum(ordered) / len(ordered),
            count=len(ordered),
        )

    def as_dict(self) -> dict:
        return {
            "p50_ms": round(self.p50, 3),
            "p95_ms": round(self.p95, 3),
            "p99_ms": round(self.p99, 3),
            "max_ms": round(self.max, 3),
            "mean_ms": round(self.mean, 3),
            "count": self.count,
        }


# --------------------------------------------------------------------------
# samples
# --------------------------------------------------------------------------


@dataclass
class Sample:
    """One request. All times are ``perf_counter`` seconds."""

    scheduled: float
    sent: float
    received: float
    status: int
    server_ms: float | None = None  # X-Custos-Latency-Ms: whole ASGI handler
    engine_ms: float | None = None  # response.latency_ms: trust engine only
    decision: str | None = None
    degraded: tuple[str, ...] = ()
    error: str | None = None

    @property
    def service_ms(self) -> float:
        return (self.received - self.sent) * 1000.0

    @property
    def response_ms(self) -> float:
        """Coordinated-omission-corrected latency: the caller's real wait."""
        return (self.received - self.scheduled) * 1000.0

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200


@dataclass
class PhaseResult:
    """Everything one rate produced."""

    rps_offered: float
    duration_s: float
    samples: list[Sample]
    connections: int
    peak_in_flight: int
    wall_s: float

    @property
    def successes(self) -> list[Sample]:
        return [s for s in self.samples if s.ok]

    @property
    def failures(self) -> list[Sample]:
        return [s for s in self.samples if not s.ok]

    @property
    def rps_achieved(self) -> float:
        return len(self.successes) / self.wall_s if self.wall_s > 0 else 0.0

    @property
    def response_time(self) -> Distribution:
        return Distribution.of([s.response_ms for s in self.successes])

    @property
    def service_time(self) -> Distribution:
        return Distribution.of([s.service_ms for s in self.successes])

    @property
    def server_time(self) -> Distribution:
        return Distribution.of([s.server_ms for s in self.successes if s.server_ms is not None])

    @property
    def engine_time(self) -> Distribution:
        return Distribution.of([s.engine_ms for s in self.successes if s.engine_ms is not None])

    @property
    def decisions(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.successes:
            if s.decision:
                counts[s.decision] = counts.get(s.decision, 0) + 1
        return counts

    @property
    def degradations(self) -> dict[str, int]:
        """How often each engine gave up, excluding the ones that always do.

        ``risk`` is a stub and is degraded on every request by design; counting
        it here would bury the engines that degraded *because of load*.
        """
        counts: dict[str, int] = {}
        for s in self.successes:
            for name in s.degraded:
                if name != "risk":
                    counts[name] = counts.get(name, 0) + 1
        return counts

    @property
    def errors(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.failures:
            label = s.error or f"HTTP {s.status}"
            counts[label] = counts.get(label, 0) + 1
        return counts

    def passed(self, budget_ms: float) -> bool:
        """The budget is on the corrected number, and no request may fail."""
        return bool(self.successes) and not self.failures and self.response_time.p99 <= budget_ms

    def as_dict(self, budget_ms: float) -> dict:
        return {
            "rps_offered": self.rps_offered,
            "rps_achieved": round(self.rps_achieved, 2),
            "duration_s": self.duration_s,
            "requests": len(self.samples),
            "ok": len(self.successes),
            "failed": len(self.failures),
            "errors": self.errors,
            "decisions": self.decisions,
            "load_induced_degradations": self.degradations,
            "connections": self.connections,
            "peak_in_flight": self.peak_in_flight,
            "response_time": self.response_time.as_dict(),
            "service_time": self.service_time.as_dict(),
            "server_handler": self.server_time.as_dict(),
            "trust_engine": self.engine_time.as_dict(),
            "budget_ms": budget_ms,
            "passed": self.passed(budget_ms),
        }


# --------------------------------------------------------------------------
# process management
# --------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Service:
    """A uvicorn subprocess.

    Subprocess rather than a thread so that the load generator's CPU time
    cannot land inside the measured latency.
    """

    def __init__(self, name: str, target: str, port: int, env: dict[str, str], workers: int = 1):
        self.name = name
        self.target = target
        self.port = port
        self.env = env
        self.workers = workers
        self.process: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            self.target,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--log-level",
            "error",
        ]
        if self.workers > 1:
            command += ["--workers", str(self.workers)]

        self.process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env={**os.environ, **self.env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def wait_healthy(self, timeout_s: float = 30.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.process is not None and self.process.poll() is not None:
                stderr = b""
                if self.process.stderr is not None:
                    stderr = self.process.stderr.read()
                raise RuntimeError(
                    f"{self.name} exited with code {self.process.returncode}:\n"
                    f"{stderr.decode(errors='replace')}"
                )
            try:
                response = httpx.get(f"{self.url}/health", timeout=1.0)
                if response.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(0.15)
        raise RuntimeError(f"{self.name} did not become healthy within {timeout_s:.0f}s")

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


# --------------------------------------------------------------------------
# fixture setup
# --------------------------------------------------------------------------


def build_payloads(count: int) -> list[dict]:
    """Realistic request bodies, reusing the demo's applicant generator.

    Every request carries a distinct feature vector. Sending one identical body
    over and over would let caching that does not exist in production make the
    numbers look good.
    """
    from examples.fintech_demo import inject_drift

    rows = inject_drift.clean_batch(n=count, seed=11)
    return [
        {
            "model_id": MODEL_ID,
            "action": "predict",
            "features": row,
            # Facts the policy rule below matches on, so the policy engine is
            # doing real parse-and-evaluate work rather than returning early.
            "context": {"region": "IN", "amount": 200_000},
        }
        for row in rows
    ]


def provision(control_url: str) -> str:
    """Tenant, model, baseline, one policy rule, one drift snapshot.

    The gateway must be measured with every engine live. A degraded engine
    short-circuits before it does any work, so benchmarking an unprovisioned
    gateway measures the error path and reports it as the hot path.
    """
    from examples.fintech_demo import inject_drift

    with httpx.Client(base_url=control_url, timeout=120.0) as client:
        response = client.post("/tenants", json={"tenant_id": TENANT_ID, "name": "Benchmark Co"})
        response.raise_for_status()
        api_key = response.json()["api_key"]
        auth = {"X-API-Key": api_key}

        client.post("/models", json={"model_id": MODEL_ID, "name": "Credit Risk v3"}, headers=auth)

        # The baseline rows are also stored as feature samples, which is what
        # the recompute below scores against.
        baseline = inject_drift.clean_batch(n=600, seed=1)
        client.post(f"/models/{MODEL_ID}/baseline", json={"samples": baseline}, headers=auth)

        client.put(
            "/config/rules",
            json={
                "rule_id": "supported-regions",
                "condition": 'region not in ["IN", "SG"]',
                "action": "veto",
                "description": "lending is licensed only in IN and SG",
            },
            headers=auth,
        )

        recompute = client.post(f"/models/{MODEL_ID}/recompute", json={}, headers=auth)
        recompute.raise_for_status()

    return api_key


# Tables the hot path appends to on every request. They grow without bound
# during a run; the configuration tables around them do not.
_HOT_TABLES = ("audit_entries", "decisions", "feature_samples")


def reset_hot_tables() -> None:
    """Empty the append-only tables, keeping tenant, model, baseline and drift.

    Without this a sweep measures a moving target. Rates are tested in
    ascending order, so by the time the interesting ones run, the database
    already holds every row the earlier phases wrote — and the highest rate,
    which is the one deciding where the ceiling lands, always runs against the
    largest database. That biases the ceiling downwards for a reason that has
    nothing to do with request rate.

    Observed directly: 200 req/s passed at p99 36.8 ms when it ran second in a
    two-rate sweep, and failed at p99 21.7 s when it ran third behind 50 and
    100. Same rate, same code, different amount of accumulated data.
    """
    from sqlalchemy import text

    from shared.db.session import session_scope

    with session_scope() as db:
        for table in _HOT_TABLES:
            db.execute(text(f"DELETE FROM {table}"))  # noqa: S608 — fixed names above


def verify_engines_live(gateway_url: str, api_key: str, payload: dict) -> list[str]:
    """One probe request. Returns the engines that came back degraded.

    Called before the run so a benchmark of a half-configured system is caught
    and reported rather than published.
    """
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{gateway_url}/v1/evaluate", json=payload, headers={"X-API-Key": api_key}
        )
        response.raise_for_status()
        return list(response.json().get("degraded_engines", []))


# --------------------------------------------------------------------------
# the generator
# --------------------------------------------------------------------------


@dataclass
class _Counter:
    value: int = 0
    peak: int = 0

    def enter(self) -> None:
        self.value += 1
        self.peak = max(self.peak, self.value)

    def exit(self) -> None:
        self.value -= 1


async def run_phase(
    gateway_url: str,
    api_key: str,
    payloads: list[dict],
    rps: float,
    duration_s: float,
    connections: int,
    request_timeout_s: float,
    collect: bool = True,
) -> PhaseResult:
    """Fire ``rps * duration_s`` requests on a fixed schedule.

    The schedule is computed once, before anything is sent. Nothing that
    happens during the run — including the server falling over — changes when a
    request was *due*, which is the whole point: the delay a backed-up server
    imposes has to be attributed to the requests that suffered it.

    In-flight requests are bounded by an explicit semaphore rather than by
    httpx's connection pool. Both cap concurrency, but only one of them does it
    cheaply: letting thousands of requests queue *inside* the pool sends its
    bookkeeping quadratic, and the generator then burns 100% of a core while
    the server it is supposed to be loading sits idle. Waiting on a semaphore
    is O(1) and FIFO, and it does not distort the measurement because latency
    is still counted from the scheduled time — a request delayed by a full
    queue records that delay, which is exactly what a real caller would see.
    """
    total = max(1, int(round(rps * duration_s)))
    url = f"{gateway_url}/v1/evaluate"
    headers = {"X-API-Key": api_key}
    samples: list[Sample] = []
    in_flight = _Counter()
    gate = asyncio.Semaphore(connections)

    limits = httpx.Limits(max_connections=connections, max_keepalive_connections=connections)
    # A generous per-request timeout rather than none. Unbounded is defensible
    # in theory — a timeout truncates the tail a p99 is asking about — but in
    # practice one wedged request hangs the whole run. Timed-out requests are
    # kept as failures carrying their full elapsed time, so they still weigh on
    # the distribution instead of quietly disappearing from it.
    timeout = httpx.Timeout(request_timeout_s)
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        # Small lead-in so task creation is not itself the first scheduling
        # delay every run reports.
        start = time.perf_counter() + 0.10
        # Past this point the phase is over. Anything still unsent is shed and
        # recorded as such: a rate the system could not absorb within its own
        # window is a failure of that rate, not a reason to run forever.
        deadline = start + duration_s + max(15.0, duration_s)

        async def fire(index: int) -> None:
            due = start + index / rps
            delay = due - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)

            if time.perf_counter() > deadline:
                if collect:
                    now = time.perf_counter()
                    samples.append(
                        Sample(
                            scheduled=due, sent=now, received=now, status=0, error="not_sent"
                        )
                    )
                return

            payload = payloads[index % len(payloads)]
            async with gate:
                sent = time.perf_counter()
                in_flight.enter()
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    received = time.perf_counter()
                    sample = Sample(
                        scheduled=due, sent=sent, received=received, status=response.status_code
                    )
                    if response.status_code == 200:
                        body = response.json()
                        sample.decision = body.get("decision")
                        sample.engine_ms = body.get("latency_ms")
                        sample.degraded = tuple(body.get("degraded_engines") or ())
                        header = response.headers.get("X-Custos-Latency-Ms")
                        sample.server_ms = float(header) if header else None
                except httpx.TimeoutException:
                    sample = Sample(
                        scheduled=due,
                        sent=sent,
                        received=time.perf_counter(),
                        status=0,
                        error="timeout",
                    )
                except Exception as exc:
                    sample = Sample(
                        scheduled=due,
                        sent=sent,
                        received=time.perf_counter(),
                        status=0,
                        error=type(exc).__name__,
                    )
                finally:
                    in_flight.exit()

            if collect:
                samples.append(sample)

        await asyncio.gather(*(fire(i) for i in range(total)))
        wall = time.perf_counter() - start

    return PhaseResult(
        rps_offered=rps,
        duration_s=duration_s,
        samples=samples,
        connections=connections,
        peak_in_flight=in_flight.peak,
        wall_s=wall,
    )


def engine_breakdown(gateway_url: str) -> dict:
    """Per-engine percentiles from the gateway's own metrics.

    Cross-checks the client-side numbers and shows where the budget goes —
    specifically whether ADR 0002 holds up, i.e. whether drift really is a
    cached read rather than a statistics computation on the hot path.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            return client.get(f"{gateway_url}/metrics.json").json().get("latency_ms", {})
    except Exception:
        return {}


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def colour_verdict(passed: bool) -> str:
    return f"{GREEN}{BOLD}PASS{RESET}" if passed else f"{RED}{BOLD}FAIL{RESET}"


def fmt(value: float) -> str:
    """Milliseconds, switching to seconds once the number stops being readable.

    A saturated run produces five-digit millisecond values. Printing "14586.86"
    next to "6.74" makes the two impossible to compare at a glance, which is
    the one thing the table exists to make easy.
    """
    if math.isnan(value):
        return "n/a"
    if value >= 10_000:
        return f"{value / 1000:.1f}s"
    return f"{value:.2f}"


def fmt_unit(value: float) -> str:
    """Same scaling as :func:`fmt`, but carrying its own unit.

    For prose, where the column header is not there to supply "ms".
    """
    if math.isnan(value):
        return "n/a"
    if value >= 10_000:
        return f"{value / 1000:.1f} s"
    return f"{value:.2f} ms"


def print_phase(result: PhaseResult, budget_ms: float, engines: dict) -> None:
    response, service = result.response_time, result.service_time
    server, engine = result.server_time, result.engine_time

    print(f"\n   {BOLD}{'latency (ms)':<22}{'p50':>10}{'p95':>10}{'p99':>10}{'max':>10}{RESET}")
    for label, dist in (
        ("response time *", response),
        ("service time", service),
        ("server handler", server),
        ("trust engine", engine),
    ):
        print(
            f"   {label:<22}{fmt(dist.p50):>10}{fmt(dist.p95):>10}"
            f"{fmt(dist.p99):>10}{fmt(dist.max):>10}"
        )

    print(f"\n   {DIM}* measured from the scheduled send time, not the actual one —{RESET}")
    print(f"   {DIM}  see benchmarks/README.md on coordinated omission{RESET}")

    if engines:
        print(f"\n   {BOLD}per-engine (server-side, p99){RESET}")
        for name, stats in sorted(engines.items()):
            if name == "gateway":
                continue
            print(f"     {name:<20}{stats.get('p99', float('nan')):>8.2f} ms")

    if result.errors:
        print(f"\n   {BOLD}{RED}errors{RESET}")
        for label, count in sorted(result.errors.items(), key=lambda kv: -kv[1]):
            print(f"     {label:<28}{count}")

    # The most consequential thing load does to this system is not make it
    # slow. It makes it answer differently: an engine that overruns
    # ENGINE_TIMEOUT_MS is cancelled and excluded from fusion, the trust score
    # is computed from fewer signals, and the verdict moves. A caller sees
    # REVIEW where an unloaded system said ALLOW — no config changed, no model
    # changed, only the arrival rate. That belongs in the report, not in a
    # footnote about latency.
    if result.degradations:
        total = len(result.successes)
        print(f"\n   {BOLD}{YELLOW}engines degraded under load{RESET}")
        for name, count in sorted(result.degradations.items(), key=lambda kv: -kv[1]):
            print(f"     {name:<20}{count:>6} / {total}  ({count / total * 100:.1f}% of requests)")

        non_allow = {d: c for d, c in result.decisions.items() if d != "ALLOW"}
        if non_allow:
            shifted = sum(non_allow.values())
            summary = ", ".join(f"{c} {d}" for d, c in sorted(non_allow.items()))
            print(
                f"     {DIM}consequence: {shifted}/{total} verdicts "
                f"({shifted / total * 100:.1f}%) came back {summary}{RESET}"
            )
            print(f"     {DIM}on traffic an unloaded gateway allows.{RESET}")

    passed = result.passed(budget_ms)
    headroom = (
        "" if math.isnan(response.p99) else f" — {response.p99 / budget_ms * 100:.0f}% of budget"
    )
    print(f"\n   {'budget':<22}{budget_ms:.0f} ms p99")
    print(f"   {'verdict':<22}{colour_verdict(passed)}  p99 {fmt_unit(response.p99)}{headroom}")

    if result.peak_in_flight >= result.connections:
        print(
            f"\n   {YELLOW}note{RESET} peak in-flight ({result.peak_in_flight}) reached the "
            f"connection\n        pool limit ({result.connections}); some queueing above is "
            f"the client's,\n        not the gateway's. Re-run with a larger --connections."
        )


def print_sweep(results: list[PhaseResult], budget_ms: float) -> None:
    print(f"\n{BOLD}{CYAN}── Sweep{RESET}\n")
    header = (
        f"   {'offered':>9}{'achieved':>11}{'p50':>10}{'p95':>10}"
        f"{'p99':>10}{'max':>10}{'errors':>8}   verdict"
    )
    print(f"{BOLD}{header}{RESET}")

    for result in results:
        dist = result.response_time
        passed = result.passed(budget_ms)
        print(
            f"   {result.rps_offered:>7.0f}/s{result.rps_achieved:>9.1f}/s"
            f"{fmt(dist.p50):>10}{fmt(dist.p95):>10}{fmt(dist.p99):>10}{fmt(dist.max):>10}"
            f"{len(result.failures):>8}   {colour_verdict(passed)}"
        )

    holding = [r for r in results if r.passed(budget_ms)]
    print()
    if not holding:
        lowest = results[0].rps_offered
        print(
            f"   {RED}{BOLD}The budget does not hold even at {lowest:.0f} req/s.{RESET} "
            "Sweep lower before drawing a ceiling."
        )
        return

    ceiling = max(r.rps_offered for r in holding)
    print(
        f"   {BOLD}Holds the {budget_ms:.0f} ms p99 budget up to "
        f"{GREEN}{ceiling:.0f} req/s{RESET}{BOLD} per instance.{RESET}"
    )
    failed = [r for r in results if not r.passed(budget_ms)]
    if failed:
        first = min(r.rps_offered for r in failed)
        print(f"   {DIM}First rate to miss it: {first:.0f} req/s.{RESET}")
    else:
        print(f"   {DIM}No tested rate missed it — the ceiling is above the sweep.{RESET}")

    # Throughput that *falls* as offered load rises is congestion collapse, not
    # a plateau. It is worth naming explicitly, because the two look similar in
    # a table and behave nothing alike in production: a plateau sheds the
    # excess, whereas collapse means a traffic spike leaves the gateway serving
    # less than it did before the spike, and staying there.
    best = max(results, key=lambda r: r.rps_achieved)
    hardest = max(results, key=lambda r: r.rps_offered)
    if hardest.rps_achieved < best.rps_achieved * 0.85:
        print(
            f"\n   {YELLOW}{BOLD}Congestion collapse.{RESET} Peak throughput is "
            f"{best.rps_achieved:.0f} req/s at {best.rps_offered:.0f} offered, but only "
            f"{hardest.rps_achieved:.0f} req/s\n   at {hardest.rps_offered:.0f} offered — "
            f"the gateway does less work under more load, not merely no more."
        )


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load-test the Custos gateway against its p99 latency budget.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--rps", type=float, default=None, help="offered rate (omit to sweep)")
    parser.add_argument("--duration", type=float, default=20.0, help="seconds per rate")
    parser.add_argument("--warmup", type=float, default=3.0, help="discarded warmup seconds")
    parser.add_argument("--connections", type=int, default=256, help="max requests in flight")
    parser.add_argument("--budget-ms", type=float, default=50.0, help="p99 budget to test against")
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=30.0,
        help="seconds before a request counts as failed (it keeps its elapsed time)",
    )
    parser.add_argument(
        "--sweep",
        type=str,
        default=None,
        help=f"comma-separated rates (default {','.join(map(str, DEFAULT_SWEEP))})",
    )
    parser.add_argument("--workers", type=int, default=1, help="uvicorn worker processes")
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="defaults to a scratch SQLite file; point at Postgres for the real number",
    )
    parser.add_argument("--json", type=Path, default=None, help="write raw results here")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    db_path = ROOT / "custos-bench.db"
    database_url = args.database_url or f"sqlite:///{db_path}"
    if args.database_url is None:
        db_path.unlink(missing_ok=True)

    os.environ["CUSTOS_DATABASE_URL"] = database_url
    from shared.db.session import create_all

    create_all(database_url)

    env = {"CUSTOS_DATABASE_URL": database_url, "PYTHONPATH": str(ROOT)}
    gateway = Service("gateway", "services.gateway.main:app", free_port(), env, args.workers)
    control = Service("control", "services.control.main:app", free_port(), env)

    rates = (
        [args.rps]
        if args.rps
        else [float(r) for r in (args.sweep.split(",") if args.sweep else DEFAULT_SWEEP)]
    )

    print(f"{BOLD}Custos — gateway load test{RESET}")

    results: list[PhaseResult] = []
    try:
        gateway.start()
        control.start()
        gateway.wait_healthy()
        control.wait_healthy()

        api_key = provision(control.url)
        payloads = build_payloads(1000)

        degraded = verify_engines_live(gateway.url, api_key, payloads[0])
        unexpected = sorted(set(degraded) - {"risk"})

        print(f"   {'gateway':<20}{gateway.url}  uvicorn, {args.workers} worker(s)")
        print(f"   {'database':<20}{database_url}")
        print(f"   {'budget':<20}{args.budget_ms:.0f} ms p99 (response time)")
        print(f"   {'connections':<20}{args.connections}")
        if degraded:
            note = "expected — RiskEngine is a stub" if not unexpected else ""
            print(f"   {'degraded engines':<20}{', '.join(degraded)}  {DIM}{note}{RESET}")
        if unexpected:
            print(
                f"\n   {RED}{BOLD}Refusing to report numbers.{RESET} "
                f"{', '.join(unexpected)} came back degraded, so the hot path\n"
                f"   under test is the error path, not the real one."
            )
            return 1

        for rate in rates:
            print(f"\n{BOLD}{CYAN}── {rate:.0f} req/s for {args.duration:.0f}s{RESET}")
            if args.warmup > 0:
                print(f"   {DIM}warming up {args.warmup:.0f}s…{RESET}")
                asyncio.run(
                    run_phase(
                        gateway.url,
                        api_key,
                        payloads,
                        rate,
                        args.warmup,
                        args.connections,
                        args.request_timeout,
                        collect=False,
                    )
                )

            # After warmup, not before: warmup traffic writes to these tables
            # too, and it is proportional to the rate, so resetting first would
            # leave exactly the bias this is meant to remove. Cache warmth is
            # unaffected — the gateway caches tenant, key, config and drift,
            # none of which live in these tables.
            reset_hot_tables()

            result = asyncio.run(
                run_phase(
                    gateway.url,
                    api_key,
                    payloads,
                    rate,
                    args.duration,
                    args.connections,
                    args.request_timeout,
                )
            )
            results.append(result)

            ok, total = len(result.successes), len(result.samples)
            print(
                f"   {'achieved':<22}{result.rps_achieved:.1f} req/s   "
                f"{ok}/{total} ok, {len(result.failures)} failed"
            )
            decisions = ", ".join(f"{k} {v}" for k, v in sorted(result.decisions.items()))
            print(f"   {'decisions':<22}{decisions or 'none'}")
            print_phase(result, args.budget_ms, engine_breakdown(gateway.url))

        if len(results) > 1:
            print_sweep(results, args.budget_ms)

    finally:
        gateway.stop()
        control.stop()

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "database_url": database_url,
                    "workers": args.workers,
                    "budget_ms": args.budget_ms,
                    "connections": args.connections,
                    "duration_s": args.duration,
                    "phases": [r.as_dict(args.budget_ms) for r in results],
                },
                indent=2,
            )
            + "\n"
        )
        print(f"\n   {DIM}raw results written to {args.json}{RESET}")

    print()
    # A sweep is *supposed* to find rates that miss the budget — that is how it
    # locates the ceiling — so only an explicit single-rate run is pass/fail,
    # which is the form worth wiring into CI.
    if args.rps and results:
        return 0 if results[0].passed(args.budget_ms) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
