# Benchmarks

> What the gateway's latency budget actually is, measured rather than asserted.

`docs/architecture.md` states G2 as a **sub-50 ms p99** on `POST /v1/evaluate`. This directory
holds the evidence for that claim, and the method used to produce it.

```bash
python -m benchmarks.load_test                        # sweep — find the ceiling
python -m benchmarks.load_test --rps 200 --duration 30
python -m benchmarks.load_test --json results.json
```

The harness starts the real gateway and control plane as **separate processes**, provisions a
tenant with a live baseline, drift snapshot and policy rule, and drives `/v1/evaluate` over real
HTTP at a controlled rate.

---

## How to read the output

Four latency series are reported, from outermost to innermost:

| Series | Measured from | What it tells you |
|---|---|---|
| **response time** | the *scheduled* send time | what a caller actually waits. **This is the number.** |
| service time | the *actual* send time | what the server took once it got the request |
| server handler | `X-Custos-Latency-Ms` | the whole ASGI handler, audit write included |
| trust engine | `latency_ms` in the body | fan-out, fusion and the decision only |

They nest. The gaps between them are where the time goes, and each gap is diagnostic:

- **response − service** is queueing. Zero while there is headroom; it explodes at saturation.
- **service − server handler** is transport, framing and the event loop.
- **server handler − trust engine** is everything the trust engine's own timer excludes —
  request validation, tenant resolution, and the synchronous audit-chain write.

That last gap is not a rounding error. See "What the first run found" below.

## Why response time is the headline number

The obvious way to write a load generator is a pool of workers in a send-wait-send loop. That
design is **closed-loop**, and it quietly corrects for the thing being measured: when the server
slows down, the generator sends less traffic, so the slow period is under-sampled and the
reported p99 comes out far better than the truth. This is Gil Tene's *coordinated omission*.

This harness is **open-loop**. Every request's send time is fixed before the run starts, and
latency is measured from that scheduled time. A request that could not be sent on time carries
the delay it really suffered.

The practical consequence: at saturation, service time can look completely healthy while
response time is an order of magnitude worse. Only one of those describes the caller's
experience. Quoting service time for a saturated system is how a slow system gets published as
a fast one.

Two further rules the harness follows:

- **Warmup is discarded.** The first requests pay for lazy imports and cold API-key and drift
  caches. Real costs, but start-up costs — averaging them into steady-state latency describes
  neither.
- **Percentiles are computed independently of `shared.telemetry.metrics`.** Measuring a system
  with its own instrument means a bug in that instrument is invisible to the test meant to
  catch it.

## Configuration matters more than the number

A p99 is meaningless without the deployment it was measured in. The harness prints the
database URL and worker count in its header, and both belong next to any number quoted from it.

- **SQLite (default).** The single-node, no-infrastructure config. Every audit append is an
  `fsync`, and writes serialise. Realistic for the demo; pessimistic for production.
- **Postgres.** What `docker-compose.yml` runs. Pass `--database-url` to measure it:

  ```bash
  docker-compose up -d postgres
  python -m benchmarks.load_test --database-url postgresql+psycopg://custos:custos@localhost/custos
  ```

`--workers N` runs uvicorn with N worker processes. Note that the per-engine breakdown is read
from one worker's `/metrics.json`, so it under-reports when `N > 1`.

---

## Results — 10 September 2026

Apple M1, 8 cores, 8 GB. macOS 26.5.1, Python 3.14. **SQLite, one uvicorn worker.**
15 s per rate, 3 s warmup discarded, 256 max in flight.

```
   offered   achieved       p50       p95       p99       max  errors   verdict
      50/s     50.0/s      8.11      8.94     10.71     23.65       0   PASS
     100/s    100.0/s      4.88      5.64     49.32    115.24       0   PASS
     200/s    200.0/s      4.15     72.87     93.66    113.53       0   FAIL
     400/s     74.0/s     31.7s     63.0s     66.4s     69.1s       0   FAIL
     600/s     78.3/s     47.3s     96.0s     99.4s    101.5s       6   FAIL
     800/s     72.5/s     69.3s    143.5s    149.6s    151.8s       4   FAIL
```

> **The gateway holds the 50 ms p99 budget up to 100 req/s per instance in this
> configuration.** Raw throughput survives to 200 req/s — 200.0 req/s achieved, zero errors —
> but the latency budget does not, at p99 94 ms.

**Quote the 100 req/s figure together with its margin, which is thin.** Across four runs of
the same command on an idle machine, p99 at that rate landed between 12 ms and 49 ms. The
budget held every time, but "p99 25 ms at 100 req/s" would be picking one draw out of that
spread. 100 req/s is where this configuration runs out of headroom, not where it sits
comfortably. At 50 req/s latency is both low and stable (p99 10.7 ms).

Reproduce with
`python -m benchmarks.load_test --sweep 50,100,200,400,600,800 --duration 15 --warmup 3`.

Three things this found, none of them visible to a single-threaded test.

### 1. The published 0.5 ms figure measures a fraction of the request

`trust_engine.evaluate` stops its timer *before* `_write_audit` runs, so the `latency_ms` it
reports — and the `custos_latency_ms{engine="gateway"}` metric derived from it — exclude the
synchronous audit-chain write. At 100 req/s:

```
trust engine      p50 0.26 ms    p99 10.18 ms     <- what the metric reports
server handler    p50 2.75 ms    p99 26.09 ms     <- the actual handler
response time     p50 4.88 ms    p99 49.32 ms     <- what the caller waits
```

The system is still inside budget, which is the good news. But the honest p99 at the ceiling is
**49 ms, not 0.5 ms** — essentially all of the budget rather than one percent of it — and the
metric is named `engine="gateway"` with nothing to suggest it stops short of the most expensive
step in the request.

### 2. The audit chain silently dropped entries under concurrency — fixed

`append_to_chain` allocates `seq` by reading the current chain head, so concurrent appends race
for the same number. The unique constraint turns that into an `IntegrityError` and the append
retries — five times, then gives up and raises. `_write_audit` catches the exception, logs it,
and returns the decision anyway with `audit_id = None`.

Measured directly against SQLite:

| concurrent writers | submitted | stored | dropped | `verify` says |
|---|---|---|---|---|
| 8 | 32 | 32 | 0 | valid |
| 10 | 40 | 39 | 1 | **valid** |
| 24 | 96 | 94 | 2 | **valid** |
| 32 | 128 | 125 | 3 | **valid** |

The last column was the serious part. **The chain verified as intact while entries were
missing.** Hash chaining detects *modification* of an entry, not *omission* of one — dropping a
write leaves every surviving link consistent with its neighbours. So `GET /audit/verify`
returned "all 125 entries verified" on a log that had lost three decisions, which for a system
whose G4 is "tamper-evident evidence for **every** decision" is the wrong kind of green light.

**Where it was actually reachable.** Not, as it first appeared, everywhere. `_write_audit` is a
synchronous call inside an `async def` handler, so a single-worker gateway serialises these
writes on the event loop and never races. Measured through the real gateway at 200 req/s:

| gateway | decisions | audit entries | missing |
|---|---|---|---|
| 1 uvicorn worker | 1200 | 1200 | 0 |
| 4 uvicorn workers | 1200 | 1198 | **2** |

So the defect appeared exactly on scaling out — which is the deployment `docker-compose.yml`
describes and §4 calls "horizontally scaled". That also ruled out the obvious fix: an
in-process lock would have protected the one configuration that was not broken, and the four
contending appenders in the broken one are in different processes and cannot see each other's
locks.

**The fix** ([`services/gateway/audit.py`](../services/gateway/audit.py)) is two parts:

- **Postgres gets a real lock.** `pg_advisory_xact_lock`, keyed per tenant, taken *before* the
  chain head is read and released at commit. This removes the race rather than coping with it.
- **Every backend gets jittered exponential backoff.** The original five retries fired with no
  delay, so all the losers of a race re-read the head at the same instant and collided with the
  same peers again — burning every attempt in a few microseconds. Jitter is what breaks the
  tie; the retry count went to 12 mostly for headroom.

After the fix: **0 entries lost at every level from 2 to 48 concurrent writers**, and 0 lost at
4 uvicorn workers.

The backoff also removed a retry storm that was amplifying load, which is why the throughput
ceiling in the table above is roughly double what it measured before the fix.

### 3. Under saturation the gateway does not just slow down — it changes its answers

This is the one worth reading twice. Past the ceiling, engines exceed `ENGINE_TIMEOUT_MS`
(20 ms), get cancelled, and are excluded from fusion per ADR 0004. The trust score is then
computed from fewer signals, and the verdict moves:

| offered | policy degraded | drift degraded | verdicts flipped to REVIEW |
|---|---|---|---|
| 50/s | 0 | 0 | 0 |
| 100/s | 0 | 0 | 0 |
| 200/s | 12 | 15 | 12 / 3000 (0.4%) |
| 400/s | 819 | 818 | **818 / 6000 (13.6%)** |
| 600/s | 725 | 727 | **723 / 8994 (8.0%)** |
| 800/s | 990 | 986 | **985 / 11996 (8.2%)** |

Same model, same code, same config, same requests — only the arrival rate changed, and past
the ceiling roughly one request in eight that an idle gateway would have allowed now routes to
a human instead.

This is the fail-safe behaving exactly as ADR 0001 and ADR 0004 specify, and it is *better*
than the alternative of inventing a trust score from missing signals. But it means a traffic
spike silently converts auto-approved transactions into review-queue backlog, which is an
operational property that belongs in the docs and on an alert, not a surprise. Note that it
begins *before* the latency budget is missed by much: at 200 req/s the flip rate is already
non-zero.

### And: throughput collapses rather than plateaus

Peak throughput is 200 req/s at 200 offered, but only ~72–78 req/s at 400 and above. Under more
load the gateway does *less* work, not merely no more — queued background feature-writes and
audit appends contend for the same SQLite write lock. A plateau sheds excess load; a collapse
means a spike leaves the gateway degraded and keeps it there, which is what makes admission
control (rather than a bigger box) the right next lever.

`tests/integration/test_concurrency.py` pins findings 1 and 2 as regression tests.
