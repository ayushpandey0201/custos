import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { DecisionValue, DriftBand } from "../api/client";
import {
  DemoClient,
  DemoUnavailable,
  type ChainCheck,
  type DemoDecision,
  type DemoStart,
  type DemoStatus,
  type DemoStep,
  type Traffic,
} from "../api/demo";
import { DemoSwitcher, NextDemo } from "./DemoSwitcher";

/* -----------------------------------------------------------------------------
 * The guided demo. Built for someone presenting Custos for the first time, in
 * front of an audience: every step says what will happen, what to say, and
 * what to point at, and each step drives the real system — nothing is canned.
 * -------------------------------------------------------------------------- */

interface StepDef {
  id: number;
  label: string;
  title: string;
  what: string;
  say: string;
  look: string;
  button: string;
  running: string;
  note?: string;
}

const STEPS: StepDef[] = [
  {
    id: 0,
    label: "Start",
    title: "Start a fresh demo",
    what:
      "Creates a brand-new company account inside Custos with its own key, plus one loan applicant we reuse in every step. Nothing is pre-recorded: every button calls the real system.",
    say:
      "We'll run a lending bot that approves loans automatically. Custos sits between the bot and the money, and decides whether each decision is allowed to go ahead.",
    look: "The applicant card on the right. The same person appears in every step.",
    button: "Start the demo",
    running: "Creating a fresh company account…",
  },
  {
    id: 1,
    label: "Unknown model",
    title: "An unknown model asks to move money",
    what:
      "The bot asks Custos to approve a ₹2.5 lakh loan, using a model that was never registered with Custos.",
    say:
      "This model has never been registered. A naive system would wave it through. Custos doesn't guess — it sends the decision to a human.",
    look: "Verdict: REVIEW. The reason says the model is not registered.",
    button: "Run step 1",
    running: "Asking Custos about an unregistered model…",
  },
  {
    id: 2,
    label: "Healthy traffic",
    title: "Register the model, send healthy traffic",
    what:
      "We register the model, show Custos 600 normal applicants as its baseline, add a business rule (lend only in India and Singapore), then send 200 normal applications through it.",
    say:
      "Now Custos knows the model and what normal looks like. On healthy traffic it stays out of the way: high trust, automatic approval.",
    look: "Drift is low. The same applicant is now ALLOWED, with a high trust score.",
    button: "Run step 2",
    running: "Sending 200 normal loan applications through Custos…",
  },
  {
    id: 3,
    label: "World changes",
    title: "The world changes",
    what:
      "We send 400 applications from a shifted population — incomes fall, credit-card utilisation spikes — and Custos measures drift. The model, the code and the settings stay exactly the same.",
    say:
      "Think of a recession arriving. The model has no idea. Custos measures how far the incoming data has moved, and exactly which inputs moved.",
    look:
      "Drift jumps to significant. Utilisation and income are blamed; credit score did not move, and is not blamed. Notice the 400 were allowed as they arrived: drift is measured over a window of traffic, then applied to the decisions that follow — which is step 4.",
    button: "Run step 3",
    running: "Sending 400 applications from a changed population…",
  },
  {
    id: 4,
    label: "Same applicant",
    title: "Same applicant, same code — a different answer",
    what: "We send the exact same application from step 2 again.",
    say:
      "Same person, same model, same code, nobody changed a setting. Earlier this was approved automatically. Now Custos holds it for a human, because the model is no longer seeing the population it was built for.",
    look: "ALLOW has become REVIEW. Read the reason aloud.",
    note:
      "If asked: on 589,186 real Lending Club loans, gating on drift did not beat random review (slide 20). This demo shows the mechanism; the study shows its limits.",
    button: "Run step 4",
    running: "Re-sending the same application…",
  },
  {
    id: 5,
    label: "Hard rule",
    title: "A hard rule, and the evidence trail",
    what:
      "We add a rule — loans above ₹5 lakh need manual sign-off — and the bot tries a ₹9 lakh loan. Then Custos checks its tamper-evident audit log.",
    say:
      "Some decisions aren't about trust scores; they're simply not allowed. This rule vetoes the loan outright. And every decision made today is chained in a log where each record locks the one before it.",
    look: "Verdict: BLOCK. The audit chain is VERIFIED.",
    button: "Run step 5",
    running: "Adding the rule and trying a ₹9 lakh loan…",
  },
  {
    id: 6,
    label: "Tamper",
    title: "Someone edits history",
    what:
      "We secretly edit the newest audit record straight in the database — turning BLOCK into ALLOW, the way someone covering their tracks would — then ask Custos to verify again.",
    say:
      "Anyone with database access can change a row. What they can't do is hide it. Watch.",
    look: "Verification fails, and names the exact record that was changed.",
    button: "Tamper with the log",
    running: "Editing the audit log behind Custos's back…",
  },
];

const FEATURE_LABELS: Record<string, string> = {
  income: "Annual income",
  utilisation: "Credit utilisation",
  bureau_score: "Credit score",
  months_employed: "Months employed",
};

const BOT_LABELS: Record<string, string> = {
  APPROVED: "Approved automatically",
  DENIED: "Declined by the model",
  HELD_FOR_REVIEW: "Held for a human",
  BLOCKED: "Blocked — no action taken",
};

function formatFeature(name: string, value: number): string {
  if (name === "utilisation") return `${Math.round(value * 100)}%`;
  if (name === "income") return Math.round(value).toLocaleString("en-IN");
  return Math.round(value).toLocaleString("en-IN");
}

function rupees(amount: number): string {
  return amount >= 100_000 ? `₹${(amount / 100_000).toFixed(1).replace(/\.0$/, "")} lakh` : `₹${amount}`;
}

/* --- small pieces ----------------------------------------------------------- */

export type IconName = "mic" | "eye" | "check" | "lock" | "alert" | "spark" | "info" | "wrench" | "user" | "flask";

export function Icon({ name }: { name: IconName }) {
  const paths: Record<string, ReactNode> = {
    mic: (
      <>
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </>
    ),
    eye: (
      <>
        <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    check: <path d="m5 12 5 5 9-10" />,
    lock: (
      <>
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
      </>
    ),
    alert: (
      <>
        <path d="M12 3 2 20h20L12 3Z" />
        <path d="M12 10v4M12 17h.01" />
      </>
    ),
    spark: <path d="M12 2v5M12 17v5M2 12h5M17 12h5M5 5l3 3M16 16l3 3M5 19l3-3M16 8l3-3" />,
    wrench: <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4 2.6-2.6Z" />,
    user: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21a8 8 0 0 1 16 0" />
      </>
    ),
    flask: <path d="M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3M7 15h10" />,
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5M12 8h.01" />
      </>
    ),
  };
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

/** Trust score on its real scale, with the BLOCK / REVIEW / ALLOW zones drawn in. */
export function TrustGauge({ value }: { value: number | null }) {
  const v = value ?? 0;
  return (
    <div className="gauge" aria-label={`trust score ${v.toFixed(2)}`}>
      <div className="gauge-track">
        <div className="gauge-zone zone-block" style={{ width: "30%" }}>BLOCK</div>
        <div className="gauge-zone zone-review" style={{ width: "30%" }}>REVIEW</div>
        <div className="gauge-zone zone-allow" style={{ width: "40%" }}>ALLOW</div>
        <div className="gauge-needle" style={{ left: `${Math.max(0, Math.min(1, v)) * 100}%` }}>
          <span>{value === null ? "—" : v.toFixed(2)}</span>
        </div>
      </div>
      <div className="gauge-scale">
        <span>0</span>
        <span style={{ left: "30%" }}>0.30</span>
        <span style={{ left: "60%" }}>0.60</span>
        <span style={{ left: "100%" }}>1.0</span>
      </div>
    </div>
  );
}

export function VerdictPill({ decision, big = false }: { decision: DecisionValue; big?: boolean }) {
  return <span className={`pill pill-${decision.toLowerCase()} ${big ? "pill-big" : ""}`}>{decision}</span>;
}

function scoreZone(score: number | null): DecisionValue | null {
  if (score === null) return null;
  return score >= 0.6 ? "ALLOW" : score >= 0.3 ? "REVIEW" : "BLOCK";
}

export function DecisionResult({ d, amount }: { d: DemoDecision; amount?: number }) {
  // When a rule decides rather than the score (an unregistered model, a veto,
  // the drift floor), the needle and the verdict disagree. Say so on screen,
  // before anyone in the room has to ask.
  const zone = scoreZone(d.trust_score);
  const overridden = zone !== null && zone !== d.custos;
  return (
    <div className={`result-decision tone-${d.custos.toLowerCase()}`}>
      <div className="result-row">
        <div>
          <div className="result-label">Custos verdict</div>
          <VerdictPill decision={d.custos} big />
        </div>
        <div className="result-bot">
          <div className="result-label">What the loan bot did</div>
          <strong>{BOT_LABELS[d.bot] ?? d.bot}</strong>
          {amount !== undefined && <span className="muted"> · loan of {rupees(amount)}</span>}
        </div>
      </div>
      <div className="result-label">Trust score</div>
      <TrustGauge value={d.trust_score} />
      {overridden && (
        <div className="override">
          <Icon name="info" /> The score alone would say <VerdictPill decision={zone} />, but a rule
          overrode it with <VerdictPill decision={d.custos} />. Rules are checked before the score.
        </div>
      )}
      <div className="result-label">Why</div>
      <p className="result-reason">{d.reason}</p>
    </div>
  );
}

export function ChainResult({ chain, tampered }: { chain: ChainCheck; tampered?: DemoStep }) {
  return (
    <div className={`chain ${chain.valid ? "chain-ok" : "chain-broken"}`}>
      <Icon name={chain.valid ? "lock" : "alert"} />
      <div>
        <div className="chain-title">
          Audit chain {chain.valid ? "VERIFIED" : `BROKEN at record #${chain.broken_at}`}
        </div>
        <div className="chain-detail">{chain.detail}</div>
        {tampered?.changed && (
          <div className="chain-edit">
            Record #{tampered.edited_seq} was edited: <VerdictPill decision={tampered.changed.from as DecisionValue} />
            {" → "}
            <VerdictPill decision={tampered.changed.to as DecisionValue} />
          </div>
        )}
      </div>
    </div>
  );
}

export function TrafficSummary({ step, noun = "applications sent" }: { step: { traffic?: Traffic }; noun?: string }) {
  if (!step.traffic) return null;
  const v = step.traffic.verdicts;
  return (
    <div className="mini-stats">
      <div>
        <span className="mini-value">{step.traffic.sent}</span>
        <span className="mini-label">{noun}</span>
      </div>
      {(["ALLOW", "REVIEW", "BLOCK"] as DecisionValue[]).map((k) => (
        <div key={k}>
          <span className={`mini-value tone-text-${k.toLowerCase()}`}>{v[k] ?? 0}</span>
          <span className="mini-label">{k}</span>
        </div>
      ))}
    </div>
  );
}

const bandOf = (s: number): DriftBand => (s < 1 / 3 ? "stable" : s < 2 / 3 ? "moderate" : "significant");

function DriftResult({ step }: { step: DemoStep }) {
  const before = step.severity_before ?? 0;
  const after = step.severity_after ?? 0;
  const maxPsi = Math.max(0.5, ...(step.features ?? []).map((f) => f.psi));
  return (
    <div className="drift-result">
      <div className="drift-jump">
        <div>
          <div className="result-label">Drift before</div>
          <div className={`drift-big band-text-${bandOf(before)}`}>{before.toFixed(3)}</div>
          <span className={`band band-${bandOf(before)}`}>{bandOf(before)}</span>
        </div>
        <div className="drift-arrow">→</div>
        <div>
          <div className="result-label">Drift after</div>
          <div className={`drift-big band-text-${bandOf(after)}`}>{after.toFixed(3)}</div>
          <span className={`band band-${bandOf(after)}`}>{bandOf(after)}</span>
        </div>
      </div>
      <div className="result-label">Which inputs moved (PSI per input)</div>
      <div className="features">
        {(step.features ?? []).map((f) => (
          <div className="feature-row" key={f.feature}>
            <span className="feature-name">{FEATURE_LABELS[f.feature] ?? f.feature}</span>
            <div className="feature-bar">
              <div className={`feature-fill fill-${f.band}`} style={{ width: `${(f.psi / maxPsi) * 100}%` }} />
            </div>
            <span className="feature-psi">{f.psi.toFixed(3)}</span>
            <span className={`band band-${f.band}`}>{f.band}</span>
          </div>
        ))}
      </div>
      <TrafficSummary step={step} />
    </div>
  );
}

function StepResult({ id, start, result }: { id: number; start: DemoStart | null; result?: DemoStep }) {
  if (id === 0 && start) {
    return (
      <div className="result-start">
        <Icon name="check" />
        <div>
          <strong>Fresh company account created: {start.tenant_id}</strong>
          <p className="muted">
            The operator console is now connected to this account automatically — open it after the
            demo to explore every decision.
          </p>
        </div>
      </div>
    );
  }
  if (!result) return null;
  if (id === 3) return <DriftResult step={result} />;
  if (id === 6 && result.chain) return <ChainResult chain={result.chain} tampered={result} />;
  return (
    <>
      {id === 2 && (
        <div className="mini-stats">
          <div>
            <span className="mini-value">{result.baseline_size}</span>
            <span className="mini-label">baseline applicants</span>
          </div>
          <div>
            <span className={`mini-value band-text-${bandOf(result.severity ?? 0)}`}>
              {(result.severity ?? 0).toFixed(3)}
            </span>
            <span className="mini-label">drift ({bandOf(result.severity ?? 0)})</span>
          </div>
          <div>
            <span className="mini-value">{result.traffic?.sent}</span>
            <span className="mini-label">healthy applications</span>
          </div>
        </div>
      )}
      {result.decision && <DecisionResult d={result.decision} amount={result.amount} />}
      {result.chain && <ChainResult chain={result.chain} />}
    </>
  );
}

/* --- the screen ---------------------------------------------------------------- */

export function GuidedDemo({ controlUrl, onKey }: {
  controlUrl: string;
  onKey: (key: string) => void;
}) {
  const client = useMemo(() => new DemoClient(controlUrl), [controlUrl]);
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [start, setStart] = useState<DemoStart | null>(null);
  const [results, setResults] = useState<Record<number, DemoStep>>({});
  const [done, setDone] = useState<Set<number>>(new Set());
  const [viewing, setViewing] = useState(0);
  const [running, setRunning] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const next = useMemo(() => STEPS.find((s) => !done.has(s.id))?.id ?? null, [done]);
  const finished = next === null;

  const poll = useCallback(async () => {
    try {
      setStatus(await client.status());
      setUnavailable(null);
    } catch (caught) {
      setUnavailable(caught instanceof DemoUnavailable ? caught.message : String(caught));
    }
  }, [client]);

  useEffect(() => {
    void poll();
    const timer = setInterval(() => void poll(), 4000);
    return () => clearInterval(timer);
  }, [poll]);

  const run = async (id: number) => {
    setRunning(id);
    setError(null);
    try {
      if (id === 0) {
        const started = await client.start();
        setStart(started);
        setResults({});
        setDone(new Set([0]));
        onKey(started.api_key);
      } else {
        const result = id === 6 ? await client.tamper() : await client.act(id);
        setResults((r) => ({ ...r, [id]: result }));
        setDone((d) => new Set([...d, id]));
      }
      setViewing(id);
      void poll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunning(null);
    }
  };

  const goNext = () => {
    if (next !== null) {
      setViewing(next);
      cardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const restart = () => {
    setStart(null);
    setResults({});
    setDone(new Set());
    setViewing(0);
    setError(null);
  };

  const step = STEPS[viewing];
  const isDone = done.has(step.id);
  const isLocked = !isDone && step.id !== next;
  const systemOk = !unavailable && status?.gateway && status?.control;

  return (
    <div className="demo">
      <DemoSwitcher current="demo" />
      <section className="demo-hero" data-tour="hero">
        <div className="eyebrow">Live demo 1 · lending</div>
        <h1>
          Watch Custos stop a model <span className="grad">the moment it can no longer be trusted.</span>
        </h1>
        <p className="lead">
          Seven steps, about four minutes. Each button drives the real system — real HTTP calls, the real
          gateway, the real database. Nothing on this screen is pre-recorded.
        </p>
      </section>

      <section className="howto card" data-tour="howto">
        <div className="howto-title">
          <Icon name="info" /> First time here? Here's how to use this screen
        </div>
        <ol className="howto-steps">
          <li><b>Check the light below is green.</b> If it's red, run <code>./app.sh</code> in a terminal and wait for it.</li>
          <li><b>Click the blue button</b> in the step card. Steps unlock one at a time, in order.</li>
          <li><b>While it runs, read the “Say this” box aloud</b> to the audience.</li>
          <li><b>When the result appears, point at what “Point at this” describes</b>, then press <b>Next step</b>.</li>
        </ol>
        <div className="syscheck" data-tour="syscheck">
          <span className={`light ${systemOk ? "light-ok" : unavailable || status ? "light-bad" : "light-wait"}`} />
          {unavailable ? (
            <span>
              <b>Custos isn't reachable.</b> {unavailable} Open a terminal in the project folder, run{" "}
              <code>./app.sh</code>, then refresh this page.
            </span>
          ) : !status ? (
            <span>Checking the system…</span>
          ) : systemOk ? (
            <span><b>System ready.</b> Gateway and control plane are both running.</span>
          ) : (
            <span>
              <b>The gateway is down.</b> Run <code>./app.sh</code> in a terminal, then wait a few seconds.
            </span>
          )}
          {systemOk && !done.has(0) && (
            <button
              className="btn btn-primary syscheck-go"
              disabled={running !== null}
              onClick={() => {
                setViewing(0);
                void run(0);
                cardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              {running === 0 ? "Starting…" : "Start the demo →"}
            </button>
          )}
        </div>
      </section>

      <nav className="stepper" aria-label="Demo steps" data-tour="stepper">
        {STEPS.map((s) => {
          const state = done.has(s.id) ? "done" : s.id === next ? "current" : "locked";
          return (
            <button
              key={s.id}
              className={`stepper-item is-${state} ${viewing === s.id ? "is-viewing" : ""}`}
              onClick={() => {
                if (state === "locked") return;
                setViewing(s.id);
                // The tabs only select a step; the button that runs it is in
                // the card below, often off-screen. Take the presenter there.
                requestAnimationFrame(() =>
                  cardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
                );
              }}
              disabled={state === "locked"}
              title={state === "locked" ? "Finish the earlier steps first" : s.title}
            >
              <span className="stepper-dot">{state === "done" ? <Icon name="check" /> : s.id === 0 ? "▶" : s.id}</span>
              <span className="stepper-label">{s.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="demo-grid" ref={cardRef}>
        <article className={`step-card card ${isLocked ? "is-locked" : ""}`} data-tour="step-card">
          <div className="step-eyebrow">
            {step.id === 0 ? "Getting started" : `Step ${step.id} of ${STEPS.length - 1}`}
            {isDone && <span className="done-tag"><Icon name="check" /> Done</span>}
          </div>
          <h2 className="step-title">{step.title}</h2>
          <p className="step-what">{step.what}</p>

          <div className="say" data-tour="say">
            <div className="say-head"><Icon name="mic" /> Say this to the audience</div>
            <p>“{step.say}”</p>
          </div>

          {!isDone && (
            <div className="step-actions">
              {isLocked ? (
                <div className="locked-note">
                  <Icon name="lock" /> Finish the earlier steps first — they build on each other.
                </div>
              ) : running === step.id ? (
                <div className="running">
                  <span className="spinner" /> {step.running}
                </div>
              ) : (
                <button className="btn btn-primary btn-xl" onClick={() => void run(step.id)} disabled={!systemOk || running !== null}>
                  {step.button}
                </button>
              )}
            </div>
          )}

          {error && running === null && !isDone && (
            <div className="error-box">
              <Icon name="alert" />
              <div>
                <b>That step didn't run.</b> {error}
                <div className="muted small">Fix the cause, then press the button again. If it fails twice, use “restart the demo” on the right — a fresh run takes seconds.</div>
              </div>
            </div>
          )}

          {isDone && (
            <div className="result" key={step.id}>
              <StepResult id={step.id} start={start} result={results[step.id]} />
              <div className="look">
                <div className="look-head"><Icon name="eye" /> Point at this</div>
                <p>{step.look}</p>
              </div>
              {step.note && (
                <div className="note-box">
                  <Icon name="info" /> {step.note}
                </div>
              )}
              <div className="step-actions">
                {!finished ? (
                  <button className="btn btn-primary btn-xl" onClick={goNext}>
                    Next step →
                  </button>
                ) : (
                  <div className="finish">
                    <div className="finish-title"><Icon name="spark" /> Demo complete</div>
                    <p className="muted">
                      Every verdict you just saw is in the audit log. Open the console to explore them,
                      or run the demo again from a clean slate.
                    </p>
                    <div className="finish-actions">
                      <NextDemo current="demo" />
                      <a className="btn" href="#/console">Open the operator console</a>
                      <button className="btn" onClick={restart}>Run the demo again</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </article>

        <aside className="demo-side" data-tour="side">
          <div className="card side-card">
            <div className="side-title">The applicant</div>
            {start ? (
              <>
                <dl className="applicant">
                  {Object.entries(start.application).map(([k, v]) => (
                    <div key={k}>
                      <dt>{FEATURE_LABELS[k] ?? k}</dt>
                      <dd>{formatFeature(k, v)}</dd>
                    </div>
                  ))}
                </dl>
                <p className="muted small">
                  Model <code>{start.model_id}</code> · the same applicant in every step, so any change in
                  the answer comes from the world changing, not the person.
                </p>
              </>
            ) : (
              <p className="muted small">Appears when you start the demo.</p>
            )}
          </div>

          <div className="card side-card">
            <div className="side-title">The three verdicts</div>
            <ul className="legend">
              <li><VerdictPill decision="ALLOW" /> Safe to act automatically.</li>
              <li><VerdictPill decision="REVIEW" /> A human must decide.</li>
              <li><VerdictPill decision="BLOCK" /> Do not act at all.</li>
            </ul>
          </div>

          <div className="card side-card">
            <div className="side-title">If something goes wrong</div>
            <ul className="trouble">
              <li><b>Red light:</b> run <code>./app.sh</code>, wait for “Custos is running”, refresh.</li>
              <li><b>A step fails twice:</b> restart the demo below; a fresh run takes seconds.</li>
              <li><b>Want a clean slate:</b> {done.size ? <button className="link" onClick={restart}>restart the demo</button> : "press Start"}.</li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
