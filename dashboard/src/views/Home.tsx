/* The landing page: what Custos is, why it is different, and the evidence.
 *
 * Every number here is either measured in this repository (benchmarks/,
 * experiments/) or cited to its public source. A landing page that overclaims is
 * the first thing a reviewer takes apart, so this one leads with what is proven
 * — including the result that went against us. */

const STATS = [
  { value: "≤ 50 ms", label: "p99 decision latency up to 200 requests/s, on one CPU core" },
  { value: "0", label: "verdicts changed by overload (was up to 985 per run)" },
  { value: "397", label: "automated tests, from statistics to tamper detection" },
  { value: "589,186", label: "real loans in our pre-registered field study" },
];

const COMPARE: { row: string; monitor: string; guard: string; custos: string }[] = [
  {
    row: "When it acts",
    monitor: "After the fact — minutes to hours",
    guard: "In real time",
    custos: "Before the action, on every request",
  },
  {
    row: "What it can stop",
    monitor: "Nothing — it raises an alert",
    guard: "Unsafe content: toxicity, personal data, jailbreaks",
    custos: "The decision itself — ALLOW, REVIEW or BLOCK",
  },
  {
    row: "What it looks at",
    monitor: "Batches of past traffic",
    guard: "The text of one request",
    custos: "Business policy, request risk and model reliability, fused",
  },
  {
    row: "When the data breaks",
    monitor: "Alerts someone to investigate",
    guard: "Not its job",
    custos: "Diagnoses it, proposes a tested repair, applies it once a person approves",
  },
  {
    row: "Evidence it leaves",
    monitor: "Charts and logs",
    guard: "Logs",
    custos: "A hash-chained record per decision; any edit is detectable",
  },
  {
    row: "If it fails",
    monitor: "Nobody notices",
    guard: "Varies",
    custos: "Fails open, loudly flagged — never takes the caller down",
  },
];

const PILLARS = [
  {
    title: "Decides, not reports",
    body:
      "Dashboards tell you a model drifted last week. Custos sits on the decision path and answers before the money moves: proceed, ask a human, or stop.",
  },
  {
    title: "Three signals, one verdict",
    body:
      "Hard business rules that can veto, per-request risk (unusual amounts, request bursts) and model reliability (drift), fused into one explainable score.",
  },
  {
    title: "Evidence nobody can quietly edit",
    body:
      "Every verdict is chained to the one before it with SHA-256. Change any past record and verification names the exact record that was touched.",
  },
  {
    title: "Safe under pressure",
    body:
      "Past capacity, Custos refuses extra requests instantly instead of queueing them — so a traffic spike can never change an answer or bring the caller down.",
  },
];

export function Home() {
  return (
    <div className="home">
      <section className="hero" data-tour="hero">
        <div className="hero-glow" aria-hidden="true" />
        <div className="eyebrow">Runtime trust layer for machine-learning decisions</div>
        <h1 className="hero-title">
          The checkpoint between <br />
          <span className="grad">your model and its decisions.</span>
        </h1>
        <p className="hero-lead">
          Models are validated once and then trusted forever. Custos checks every consequential
          decision at the moment it happens — and refuses to let a model act when it can no longer
          be trusted. Credit, fraud, claims, triage or an AI agent spending money: if a model's
          output triggers an action, Custos can gate it.
        </p>
        <div className="hero-cta">
          <a className="btn btn-primary btn-xl" href="#/demo">Watch the live demo →</a>
          <a className="btn btn-ghost btn-xl" href="#/docs">Read the documentation</a>
        </div>
        <div className="stats" data-tour="stats">
          {STATS.map((s) => (
            <div className="stat" key={s.label}>
              <div className="stat-big">{s.value}</div>
              <div className="stat-small">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">The problem</div>
          <h2>Models don't crash. They go quietly wrong.</h2>
        </div>
        <div className="problem" data-tour="problem">
          <div className="problem-text">
            <p>
              A credit model is tested before launch and then left alone. The world keeps moving —
              incomes fall, spending changes — and the model keeps answering with exactly the
              confidence it had on day one. Nothing errors. Nothing alerts. Drift gets checked on a
              quarterly report, but decisions are made every second.
            </p>
            <p>
              In 2021 Zillow's home-buying algorithm kept making offers as the market moved underneath
              it. Every offer looked reasonable on its own. By November the company wrote down
              <b> $304 million in one quarter</b>, shut the business, and <b>2,000 people lost their
              jobs</b>. The model never crashed.
            </p>
            <p className="cite">Source: Zillow Group Q3 2021 results and SEC filings.</p>
          </div>
          <div className="timeline-card card">
            <div className="tl-row">
              <span className="tl-dot tl-blue" />
              <div><b>Quarterly report</b><span className="muted"> — model looks fine</span></div>
            </div>
            <div className="tl-gap">
              <span className="tl-dot tl-red" />
              <div><b>The population shifts</b><span className="muted"> — no one notices</span></div>
            </div>
            <div className="tl-window">
              <b>~11 weeks</b> of automated decisions made by a model nobody knows has drifted
            </div>
            <div className="tl-row">
              <span className="tl-dot tl-blue" />
              <div><b>Next report</b><span className="muted"> — the damage is already done</span></div>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">How we are different</div>
          <h2>Monitoring reports. Guardrails filter content. Custos decides.</h2>
        </div>
        <div className="compare card" data-tour="compare">
          <table>
            <thead>
              <tr>
                <th />
                <th>Monitoring dashboards</th>
                <th>Content guardrails</th>
                <th className="col-custos">Custos</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE.map((r) => (
                <tr key={r.row}>
                  <td className="row-label">{r.row}</td>
                  <td>{r.monitor}</td>
                  <td>{r.guard}</td>
                  <td className="col-custos">{r.custos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small compare-note">
          Examples of each category: monitoring — Evidently, Arize, Fiddler, SageMaker Model Monitor;
          guardrails — NeMo Guardrails, Bedrock Guardrails.
        </p>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">What we bring</div>
          <h2>Four guarantees, each one tested.</h2>
        </div>
        <div className="pillars" data-tour="pillars">
          {PILLARS.map((p, i) => (
            <div className="pillar card" key={p.title}>
              <div className="pillar-num">0{i + 1}</div>
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">Governed self-healing</div>
          <h2>When a data feed breaks, Custos proposes the fix. A person decides.</h2>
        </div>
        <div className="pillars" data-tour="healing">
          <div className="pillar card">
            <div className="pillar-num">Diagnose</div>
            <h3>Broken pipe or changed world?</h3>
            <p>
              A credit-score feed stuck at one value and a real recession both look like “drift”. Custos
              tells them apart — because the right repair for one is the wrong repair for the other.
            </p>
          </div>
          <div className="pillar card">
            <div className="pillar-num">Test</div>
            <h3>Shadow-tested on real decisions</h3>
            <p>
              Every proposed repair is replayed on the model's recent real decisions — up to 500 — through
              the same decision logic, so the reviewer sees exactly how many verdicts it would change.
            </p>
          </div>
          <div className="pillar card">
            <div className="pillar-num">Approve</div>
            <h3>A named person decides</h3>
            <p>
              Nothing changes until someone approves — and a repair that failed its test can't be. Their
              name goes on the same tamper-evident chain as every decision.
            </p>
          </div>
          <div className="pillar card">
            <div className="pillar-num">Refuse</div>
            <h3>It knows what not to do</h3>
            <p>
              It will never re-learn “normal” from a broken feed, and it never claims to retrain a model it
              doesn't own. Those are recorded as requests, with evidence.
            </p>
          </div>
        </div>
        <p className="compare-note">
          <a className="btn btn-ghost" href="#/healing">See a data feed break and get repaired, live →</a>
        </p>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">What changes</div>
          <h2>Before and after Custos.</h2>
        </div>
        <div className="beforeafter" data-tour="beforeafter">
          <div className="ba card ba-before">
            <h3>Without Custos</h3>
            <ul>
              <li>A drifted model approves loans for weeks until a report notices.</li>
              <li>An unregistered or experimental model can move real money.</li>
              <li>Decision logs can be edited, and nobody can prove they were.</li>
              <li>A traffic spike slows everything down — or quietly changes answers.</li>
              <li>A dead data feed keeps the model approving on garbage until someone notices.</li>
            </ul>
          </div>
          <div className="ba card ba-after">
            <h3>With Custos</h3>
            <ul>
              <li>Every consequential decision is checked before it executes.</li>
              <li>Unknown models and policy breaches go to a human or are stopped.</li>
              <li>Every verdict is provable; any edit is detected and located.</li>
              <li>Overload is refused cleanly; answers never change under load.</li>
              <li>A dead feed is diagnosed, and decisions are held the moment a person approves the repair.</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">Proof, not promises</div>
          <h2>We test our own claims — and publish when they fail.</h2>
        </div>
        <div className="proof" data-tour="proof">
          <div className="proof-card card">
            <div className="proof-tag tag-ok">Calibrated</div>
            <h3>The detector measures correctly</h3>
            <p>
              Feed it a shift of a known size and check the reading. No shift reads <b>0.030</b>{" "}
              (stable); a one-standard-deviation shift reads <b>1.019</b> — four times the industry's
              “significant” line.
            </p>
          </div>
          <div className="proof-card card">
            <div className="proof-tag tag-ok">Load-tested</div>
            <h3>Fast, and safe when overloaded</h3>
            <p>
              An open-loop load test that cannot flatter us: the 50 ms budget holds to{" "}
              <b>200 requests/s</b>, double our previous ceiling, and overload changes <b>zero</b>{" "}
              verdicts.
            </p>
          </div>
          <div className="proof-card card proof-honest">
            <div className="proof-tag tag-warn">Pre-registered — and it went against us</div>
            <h3>Drift alone is not the right gate</h3>
            <p>
              On <b>589,186 real loans</b>, gating on population drift caught <b>fewer</b> defaults
              than random review; the model's own risk ranking caught <b>2.1×</b> more. We wrote the
              test down before seeing the data, published the result, and are rebuilding the gate
              around it.
            </p>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div className="eyebrow">Integration</div>
          <h2>Five lines in the service you already have.</h2>
        </div>
        <div className="integrate" data-tour="integrate">
          <pre className="code card">
{`import custos
custos.configure(base_url="http://localhost:8000", api_key=KEY)

@custos.guard(model_id="credit-risk-v3", action="disburse",
              features="application")
def disburse(*, application):
    ...   # runs only if Custos says ALLOW`}
          </pre>
          <ul className="integrate-points">
            <li><b>BLOCK</b> raises <code>custos.Blocked</code> — the action never runs.</li>
            <li><b>REVIEW</b> raises <code>custos.ReviewRequired</code> — your code must route it to a person.</li>
            <li><b>Custos down?</b> The call proceeds, flagged <code>failed_open</code> — never silently.</li>
            <li><b>No dependencies:</b> the SDK uses only Python's standard library.</li>
          </ul>
        </div>
      </section>

      <section className="cta-band card" data-tour="cta">
        <div>
          <h2>See it decide, live.</h2>
          <p className="muted">
            Three guided demos on the real system, about ten minutes: a lending model that drifts, a data feed that
            breaks and gets repaired, and an AI agent issuing refunds — a second domain, with no code changed.
          </p>
        </div>
        <a className="btn btn-primary btn-xl" href="#/demo">Start the live demo →</a>
      </section>
    </div>
  );
}
