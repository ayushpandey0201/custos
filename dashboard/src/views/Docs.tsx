import { useEffect, useState } from "react";
import type { ReactNode } from "react";

/* Documentation: everything a first-time reader needs, in one scrollable page
 * with a sidebar that tracks where you are. Written for someone who has never
 * seen the project — an examiner, a new teammate, an operator. */

interface Section {
  id: string;
  title: string;
  body: ReactNode;
}

function Code({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="doc-code">
      <pre>{children}</pre>
      <button
        className="copy"
        onClick={() => {
          void navigator.clipboard?.writeText(children);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

const SECTIONS: Section[] = [
  {
    id: "overview",
    title: "Overview",
    body: (
      <>
        <p>
          <b>Custos</b> (Latin for <i>guard</i>) is a runtime trust layer for machine-learning
          models. It sits between a model and the consequential action taken on its output — paying
          out a loan, moving money, approving a claim — and answers one question on every request:
        </p>
        <blockquote>
          Given everything we currently know about this model and this request, should this
          decision go ahead?
        </blockquote>
        <p>The answer is always one of three verdicts:</p>
        <table className="doc-table">
          <tbody>
            <tr><td><span className="pill pill-allow">ALLOW</span></td><td>Safe to act automatically.</td></tr>
            <tr><td><span className="pill pill-review">REVIEW</span></td><td>A human must decide before anything happens.</td></tr>
            <tr><td><span className="pill pill-block">BLOCK</span></td><td>Do not act at all.</td></tr>
          </tbody>
        </table>
        <h4>What Custos is not</h4>
        <ul>
          <li>It does not train, serve or host models — it observes and gates them.</li>
          <li>It does not explain individual predictions.</li>
          <li>It does not retrain or roll back a model. It decides and records; humans act.</li>
          <li>It is not a user-authentication system; its policy rules are about how models are used.</li>
        </ul>
      </>
    ),
  },
  {
    id: "quickstart",
    title: "Quick start",
    body: (
      <>
        <p>From the project folder, one command starts everything:</p>
        <Code>./app.sh</Code>
        <ul>
          <li><b>Gateway</b> (decisions) on <code>http://localhost:8000</code></li>
          <li><b>Control plane</b> (setup, history, audit) on <code>http://localhost:8001</code></li>
          <li><b>This dashboard</b> on <code>http://localhost:5173</code></li>
        </ul>
        <p>
          It seeds a demo company, prints its API key and saves it to <code>.run/api-key.txt</code>.
          Running it again is safe: if everything is already up it just prints the links.
        </p>
        <table className="doc-table">
          <thead><tr><th>Command</th><th>What it does</th></tr></thead>
          <tbody>
            <tr><td><code>./app.sh</code></td><td>Start whatever isn't running; never restarts a healthy server.</td></tr>
            <tr><td><code>./app.sh --open</code></td><td>Same, then opens the dashboard in your browser.</td></tr>
            <tr><td><code>./app.sh --restart</code></td><td>Stop everything and start fresh. The API key changes.</td></tr>
            <tr><td><code>./stop.sh</code></td><td>Stop every Custos process and free all three ports.</td></tr>
          </tbody>
        </table>
        <p>
          The fastest way to understand the system is the <a href="#/demo">live demo</a>: seven guided
          steps, about four minutes, each with instructions on screen.
        </p>
      </>
    ),
  },
  {
    id: "concepts",
    title: "Key concepts",
    body: (
      <table className="doc-table doc-glossary">
        <tbody>
          <tr><td>Model</td><td>A program that learned a pattern from past data, e.g. “will this applicant repay?”</td></tr>
          <tr><td>Drift</td><td>Live data no longer looks like the data the model learned from. The model doesn't crash — it goes quietly wrong.</td></tr>
          <tr><td>Baseline</td><td>A frozen snapshot of what the data looked like when the model was built. Everything is compared to it.</td></tr>
          <tr><td>PSI</td><td>Population Stability Index: one number for how far today's data has moved from the baseline. Under 0.10 stable, 0.10–0.25 moderate, above 0.25 significant — the bands banks already use.</td></tr>
          <tr><td>KS statistic</td><td>A second, independent measure of the same movement. Custos lets it raise a drift reading, never lower one.</td></tr>
          <tr><td>Severity</td><td>All per-input drift readings combined into one score from 0 to 1.</td></tr>
          <tr><td>Engine</td><td>One independent check. Custos has three: policy, drift and risk.</td></tr>
          <tr><td>Trust score</td><td>The engines' answers fused into one number from 0 to 1.</td></tr>
          <tr><td>Veto</td><td>A policy rule overriding everything else, forcing BLOCK.</td></tr>
          <tr><td>Degraded</td><td>An engine with no confident answer. It is left out of the score, never counted as “safe”.</td></tr>
          <tr><td>Fail-open</td><td>If Custos itself fails, the caller proceeds — loudly flagged — rather than being taken down.</td></tr>
          <tr><td>Hash chain</td><td>Each audit record is cryptographically locked to the previous one, so editing any record is detectable.</td></tr>
          <tr><td>Tenant</td><td>One customer company. Each has its own key, models, rules and audit chain, invisible to others.</td></tr>
          <tr><td>p99 latency</td><td>99 of every 100 requests finish faster than this. Fairer than an average.</td></tr>
        </tbody>
      </table>
    ),
  },
  {
    id: "decision",
    title: "How a decision is made",
    body: (
      <>
        <p>One call to <code>POST /v1/evaluate</code>, start to finish:</p>
        <ol className="doc-flow">
          <li><b>Authenticate.</b> The API key is hashed and matched to a tenant (cached).</li>
          <li><b>Admit.</b> If the gateway already holds its limit of in-flight requests, it answers 503 immediately instead of queueing.</li>
          <li><b>Ask the three engines at the same time</b>, each with a 20 ms limit. An engine that overruns is marked degraded.</li>
          <li><b>Fuse</b> the answers into a weighted trust score (drift 0.5, policy 0.3, risk 0.2), leaving degraded engines out.</li>
          <li><b>Decide</b> with the cascade below.</li>
          <li><b>Record</b> the verdict in the tamper-evident audit chain, then reply.</li>
        </ol>
        <h4>The decision cascade — evaluated in this order</h4>
        <table className="doc-table">
          <thead><tr><th>#</th><th>If…</th><th>Then</th></tr></thead>
          <tbody>
            <tr><td>1</td><td>any engine vetoes</td><td><span className="pill pill-block">BLOCK</span></td></tr>
            <tr><td>2</td><td>trust score is below 0.30</td><td><span className="pill pill-block">BLOCK</span></td></tr>
            <tr><td>3</td><td>the model was never registered</td><td><span className="pill pill-review">REVIEW</span></td></tr>
            <tr><td>4</td><td>every engine is degraded</td><td><span className="pill pill-review">REVIEW</span></td></tr>
            <tr><td>5</td><td>drift is in the significant band (the drift floor)</td><td><span className="pill pill-review">REVIEW</span></td></tr>
            <tr><td>6</td><td>trust score is below 0.60</td><td><span className="pill pill-review">REVIEW</span></td></tr>
            <tr><td>7</td><td>otherwise</td><td><span className="pill pill-allow">ALLOW</span></td></tr>
          </tbody>
        </table>
        <p className="doc-callout">
          <b>Note on rule 5.</b> In our pre-registered study on real loans, drift-based gating did not
          beat random review, and the drift floor would have escalated 92% of decisions. It stays as a
          safety rule today; the gate is being rebuilt around risk-ranked review. See{" "}
          <a href="#validation" onClick={(e) => { e.preventDefault(); document.getElementById("validation")?.scrollIntoView({ behavior: "smooth" }); }}>Validation</a>.
        </p>
      </>
    ),
  },
  {
    id: "signals",
    title: "The three signals",
    body: (
      <>
        <h4>Policy — “is this action allowed?”</h4>
        <p>
          Business rules written as plain conditions over the request. They are parsed by a real
          grammar and never executed as code, so a rule can't become a security hole.
        </p>
        <Code>{`action == "disburse" and amount > 500000      → veto
region not in ["IN", "SG"]                     → veto`}</Code>
        <p className="muted small">
          Operators: <code>==  !=  &gt;  &gt;=  &lt;  &lt;=  in  not in</code>, combined with{" "}
          <code>and</code>, <code>or</code>, <code>not</code> and parentheses.
        </p>
        <h4>Drift — “does the model still fit its traffic?”</h4>
        <p>
          An offline worker compares recent inputs against the frozen baseline with PSI and KS, per
          input, and stores a severity. The request path only reads that stored number, which is how
          a full statistical check fits inside a 50 ms budget. Drift is also attributed: it names
          <i> which</i> inputs moved — the difference between the world changing and one data feed
          breaking.
        </p>
        <h4>Risk — “is this one request unusual?”</h4>
        <ul>
          <li><b>Amount:</b> how far the amount sits above this company's typical amounts, using the median, so a few extreme values can't distort “normal”.</li>
          <li><b>Velocity:</b> how many requests one customer made in the last minute — bursts are a classic fraud and runaway-agent pattern.</li>
          <li>The worst of the two decides; with too little history, the engine abstains rather than guess.</li>
        </ul>
      </>
    ),
  },
  {
    id: "architecture",
    title: "Architecture",
    body: (
      <>
        <p>Two planes, so that everything slow stays off the path a customer is waiting on.</p>
        <table className="doc-table">
          <thead><tr><th>Part</th><th>Role</th></tr></thead>
          <tbody>
            <tr><td>Gateway</td><td>The hot path. Authenticates, admits, fans out to engines, fuses, decides, records.</td></tr>
            <tr><td>Engines</td><td>Policy, drift and risk. They never import each other — adding a fourth is a new file, not a refactor.</td></tr>
            <tr><td>Control plane</td><td>Tenants, model registration, baselines, rules, configuration, drift history, audit retrieval.</td></tr>
            <tr><td>Drift worker</td><td>Computes PSI and KS offline on a schedule. No statistics on the request path.</td></tr>
            <tr><td>Storage</td><td>SQLite on one machine, PostgreSQL + Redis in production. Every table carries the tenant id.</td></tr>
            <tr><td>Python SDK</td><td>The integration: a decorator or a context manager. Standard library only.</td></tr>
            <tr><td>Dashboard</td><td>This app: guided demo, documentation and the operator console.</td></tr>
          </tbody>
        </table>
      </>
    ),
  },
  {
    id: "safety",
    title: "Safety guarantees",
    body: (
      <ul className="doc-guarantees">
        <li><b>Degraded is not trusted.</b> An engine with no answer is excluded from the score and named in the reasons — never defaulted to “safe”.</li>
        <li><b>Unknown models never auto-approve.</b> A model Custos has never seen goes to REVIEW.</li>
        <li><b>Fail-open, loudly.</b> If Custos is unreachable, the SDK lets the call through with <code>failed_open=True</code>. Companies that need the opposite set fail-closed.</li>
        <li><b>Overload is refused, not queued.</b> Past capacity the gateway answers 503 at once; load never changes a verdict.</li>
        <li><b>Tamper-evident audit.</b> Every verdict is hash-chained. Verification reports the first record that was altered.</li>
        <li><b>Keys stored hashed.</b> Only a SHA-256 of each API key is stored; a database leak yields no working keys.</li>
        <li><b>Tenant isolation.</b> Every query is scoped by tenant.</li>
      </ul>
    ),
  },
  {
    id: "sdk",
    title: "Integrating with the SDK",
    body: (
      <>
        <Code>{`import custos
custos.configure(base_url="http://localhost:8000", api_key=KEY)

@custos.guard(model_id="credit-risk-v3", action="disburse", features="application")
def disburse(*, application):
    ...  # runs only on ALLOW`}</Code>
        <p>Or wrap just the risky part:</p>
        <Code>{`with custos.gate(model_id="credit-risk-v3", action="disburse",
                features=application, context={"amount": amount}) as verdict:
    pay_out(amount)`}</Code>
        <ul>
          <li><code>custos.Blocked</code> is raised on BLOCK — the action never runs.</li>
          <li><code>custos.ReviewRequired</code> is raised on REVIEW — route it to a person.</li>
          <li><code>features</code> feed drift; <code>context</code> feeds policy rules and risk.</li>
        </ul>
      </>
    ),
  },
  {
    id: "api",
    title: "API reference",
    body: (
      <>
        <p>Every control-plane call except tenant creation needs the header <code>X-API-Key</code>.</p>
        <table className="doc-table doc-api">
          <thead><tr><th>Method</th><th>Path</th><th>Purpose</th></tr></thead>
          <tbody>
            <tr className="api-group"><td colSpan={3}>Gateway · port 8000</td></tr>
            <tr><td>POST</td><td>/v1/evaluate</td><td>Get a verdict for one decision</td></tr>
            <tr><td>GET</td><td>/health</td><td>Is the gateway up</td></tr>
            <tr><td>GET</td><td>/metrics, /metrics.json</td><td>Counters and latency percentiles</td></tr>
            <tr className="api-group"><td colSpan={3}>Control plane · port 8001</td></tr>
            <tr><td>POST</td><td>/tenants</td><td>Create a company; returns its API key once</td></tr>
            <tr><td>GET · POST</td><td>/models</td><td>List or register models</td></tr>
            <tr><td>POST</td><td>/models/{"{id}"}/baseline</td><td>Capture the reference distribution</td></tr>
            <tr><td>POST</td><td>/models/{"{id}"}/recompute</td><td>Recompute drift now</td></tr>
            <tr><td>GET</td><td>/models/{"{id}"}/drift</td><td>Drift history and per-input attribution</td></tr>
            <tr><td>GET · PUT</td><td>/config</td><td>Weights, thresholds, engines, fail-open</td></tr>
            <tr><td>GET · PUT · DELETE</td><td>/config/rules</td><td>Policy rules</td></tr>
            <tr><td>GET</td><td>/audit, /audit/decisions</td><td>Audit records and recent decisions</td></tr>
            <tr><td>GET</td><td>/audit/verify</td><td>Recompute the hash chain; report the first broken record</td></tr>
            <tr><td>GET</td><td>/audit/export</td><td>Download the evidence</td></tr>
            <tr className="api-group"><td colSpan={3}>Demo mode only (./app.sh)</td></tr>
            <tr><td>GET · POST</td><td>/demo/status, /demo/start, /demo/act/{"{1-5}"}, /demo/tamper</td><td>Drive the guided demo</td></tr>
          </tbody>
        </table>
        <p className="muted small">Interactive docs: <code>http://localhost:8000/docs</code> and <code>http://localhost:8001/docs</code>.</p>
      </>
    ),
  },
  {
    id: "console",
    title: "Using the operator console",
    body: (
      <ul>
        <li><b>Models</b> — registered models, whether each has a baseline, and a button to recompute drift.</li>
        <li><b>Drift monitor</b> — the selected model's severity over time and which inputs moved.</li>
        <li><b>Decisions</b> — every recent verdict, with its trust score and reasons.</li>
        <li><b>Audit log</b> — the hash-chained record; <i>Verify chain</i> recomputes it and reports any tampering.</li>
        <li>The <b>Explanations</b> switch adds a plain-English description to every panel.</li>
      </ul>
    ),
  },
  {
    id: "validation",
    title: "Validation and results",
    body: (
      <>
        <h4>Calibration — is the detector correct?</h4>
        <p>
          Custos learns nothing from data; it measures. So it is validated like an instrument: shifts
          of a known size go in, and the readings are checked. No shift reads 0.030 (stable); a
          one-standard-deviation shift reads 1.019 — four times the “significant” line. The reading
          rises with every step, never falling.
        </p>
        <h4>Load — is it fast and safe?</h4>
        <p>
          An open-loop load test (it can't flatter the result by slowing down when the server does)
          shows the 50 ms p99 budget holding to 200 requests/s per instance — p99 28 ms — and zero
          verdicts changed by overload.
        </p>
        <h4>Field study — does gating on drift actually help?</h4>
        <p>
          Pre-registered: the hypotheses were committed and published before the data was downloaded.
          On 589,186 real Lending Club loans (2012–2015), each strategy chose 5% of loans for human
          review:
        </p>
        <table className="doc-table">
          <thead><tr><th>Strategy</th><th>Defaults caught per 1,000 reviews</th></tr></thead>
          <tbody>
            <tr><td>Model's own risk score</td><td><b>292</b> (2.1× random)</td></tr>
            <tr><td>Risk + novelty blend</td><td>280</td></tr>
            <tr><td>Custos adaptive (proposed)</td><td>274</td></tr>
            <tr><td>Per-request novelty</td><td>188</td></tr>
            <tr><td>Random review</td><td>140</td></tr>
            <tr><td>Population drift (Custos today)</td><td><b>126 — worse than random</b></td></tr>
          </tbody>
        </table>
        <p>
          Drift peaked when Lending Club repriced its loans — quarters that turned out safer than
          average — and it read “significant” in 13 of 16 quarters, so it could not rank anything.
          The gate is being rebuilt around risk-ranked review, with drift kept as a monitoring
          signal. Full write-up: <code>experiments/gating/RESULTS_v1.md</code>.
        </p>
      </>
    ),
  },
  {
    id: "limitations",
    title: "Limitations",
    body: (
      <ul>
        <li>Drift gating did not beat random review on real loans; the gate is being redesigned.</li>
        <li>One field dataset so far — a second is needed before any general claim.</li>
        <li>Input drift only: Custos does not measure concept drift, because real outcomes arrive months later.</li>
        <li>Load measured on one machine with SQLite; past ~300 requests/s one process saturates. Scaling out is planned.</li>
        <li>Risk-engine history is per process; a shared store is the multi-server step.</li>
      </ul>
    ),
  },
  {
    id: "faq",
    title: "FAQ and troubleshooting",
    body: (
      <dl className="doc-faq">
        <dt>The dashboard says Custos isn't reachable.</dt>
        <dd>Run <code>./app.sh</code> in the project folder and wait for “Custos is running”, then refresh.</dd>
        <dt>The console shows an invalid-key error.</dt>
        <dd>The demo was restarted, which creates a new key. Run the live demo again, or paste the key from <code>.run/api-key.txt</code>.</dd>
        <dt>A port is “in use but not answering as Custos”.</dt>
        <dd>Something else holds the port. Run <code>./stop.sh</code>, or find it with <code>lsof -i tcp:8000</code>.</dd>
        <dt>Why three verdicts instead of two?</dt>
        <dd>Full automation is too risky and full manual review too expensive; REVIEW is what makes the system usable.</dd>
        <dt>Isn't this just monitoring?</dt>
        <dd>Monitoring reports after the fact. Custos runs before the action and can stop it.</dd>
      </dl>
    ),
  },
];

export function Docs() {
  const [active, setActive] = useState(SECTIONS[0].id);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-90px 0px -65% 0px" },
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <div className="docs">
      <aside className="docs-nav">
        <div className="docs-nav-title">Documentation</div>
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            className={`docs-link ${active === s.id ? "is-active" : ""}`}
            onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
          >
            {s.title}
          </button>
        ))}
      </aside>
      <article className="docs-body">
        <header className="docs-head">
          <div className="eyebrow">Documentation</div>
          <h1>Everything you need to know about Custos</h1>
          <p className="lead">From running it for the first time to how every verdict is made — and what our own tests say about it.</p>
        </header>
        {SECTIONS.map((s) => (
          <section className="doc-section" id={s.id} key={s.id}>
            <h2>{s.title}</h2>
            {s.body}
          </section>
        ))}
      </article>
    </div>
  );
}
