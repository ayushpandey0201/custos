import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ControlApiClient } from "../api/client";
import { DemoClient, DemoUnavailable, type HealingStart, type HealingStatus, type HealingStep } from "../api/demo";
import { ChainResult, DecisionResult, Icon, TrafficSummary } from "./GuidedDemo";
import { ApproverField, IncidentCard, IncidentQueue, useApprover } from "./IncidentQueue";

/* -----------------------------------------------------------------------------
 * Governed self-healing: what it is, a guided run on the real system, and the
 * live approval queue. Same conventions as the main demo — every button calls
 * the real system, every step says what to say and what to point at.
 * -------------------------------------------------------------------------- */

const LOOP = [
  { name: "Detect", body: "Every drift recompute also checks each input feed." },
  { name: "Diagnose", body: "Broken feed (stuck or missing) or a real population shift?" },
  { name: "Propose", body: "A repair Custos can actually make — and what it refuses to." },
  { name: "Shadow test", body: "Replayed on up to 500 of the model's recent real decisions." },
  { name: "Human approves", body: "A named person decides. Failed tests cannot be approved." },
  { name: "Apply", body: "Takes effect on the next request." },
  { name: "Verify", body: "Measured on fresh traffic; proposes release or rollback." },
];

const PLAYBOOK = [
  {
    diagnosis: "Broken data feed",
    detail: "an input stuck at one value, or missing",
    repair: "Quarantine the input: hold the model's decisions for review until the feed is fixed, then release — both approved by a person.",
    refuses: "Re-baselining. Learning a new reference from broken data would teach the alarm that broken is normal.",
  },
  {
    diagnosis: "Population shift",
    detail: "inputs arriving normally, but the population moved",
    repair: "Accept the new population as the reference (undoable), or record a retrain request for the model's owner.",
    refuses: "Re-baselining while the population is still moving — the hold-out test fails, and a failed test cannot be approved.",
  },
];

interface StepDef {
  id: number;
  label: string;
  title: string;
  what: string;
  say: string;
  look: string;
  button: string;
  running: string;
  needsName?: boolean;
}

const STEPS: StepDef[] = [
  {
    id: 0,
    label: "Healthy",
    title: "Start with a healthy lender",
    what:
      "Creates a fresh company account, registers the lending model, shows Custos 600 normal applicants as its baseline, and sends 200 normal applications through it.",
    say:
      "This is a lender on a normal day. The model is registered, Custos knows what normal looks like, and decisions flow automatically.",
    look: "Drift is stable, and our applicant is approved automatically.",
    button: "Start the self-healing demo",
    running: "Setting up a healthy lender and sending 200 applications…",
  },
  {
    id: 1,
    label: "Feed breaks",
    title: "The credit-bureau feed dies",
    what:
      "The credit bureau's API goes down. The lender's pipeline quietly fills every credit score with a default of 720 and carries on. We send 200 applications through it, then Custos runs its regular check.",
    say:
      "This is the most common failure in production machine learning — not a recession, a broken pipe. Watch the model: it keeps approving loans. Nothing crashes. Nothing errors.",
    look:
      "The model let these applications through: it kept working on garbage. Then Custos diagnosed it — credit score stuck at one value in 100% of requests — and proposed a quarantine. Point at what it refused to propose, and why.",
    button: "Break the feed",
    running: "Sending 200 applications with a dead credit-score feed…",
  },
  {
    id: 2,
    label: "Approve",
    title: "A person approves the repair",
    what:
      "Custos has proposed a repair and shadow-tested it on the model's recent real decisions. It changes nothing until a named person approves it. Type your name, then approve.",
    say:
      "This is the difference from autonomous self-healing. Custos detects, diagnoses, proposes and tests — but a person decides, and their name goes on the record.",
    look: "The same applicant is now held for a human. The reason names the broken input and the incident.",
    button: "Approve the quarantine",
    running: "Recording your approval and applying the quarantine…",
    needsName: true,
  },
  {
    id: 3,
    label: "Feed fixed",
    title: "The data team repairs the feed",
    what:
      "The bureau is back and 200 normal applications arrive. Custos re-checks the feed on fresh traffic, finds it healthy, and proposes releasing the hold — with its own shadow test.",
    say:
      "Custos verifies its own repair. It doesn't assume the problem has gone away; it measures it, on traffic that arrived after the fix.",
    look: "Verification: the feed is healthy. A release is proposed — and it needs a person too.",
    button: "Fix the feed",
    running: "Sending 200 applications through the repaired feed…",
  },
  {
    id: 4,
    label: "Release",
    title: "Approve the release",
    what: "Approve releasing the quarantine. Decisions flow automatically again.",
    say:
      "The hold is lifted by a person, on evidence. And because the broken period is excluded from drift, the model is trusted again straight away — not tomorrow.",
    look: "Our applicant is approved automatically again, and the incident is resolved.",
    button: "Approve the release",
    running: "Recording your approval and releasing the hold…",
    needsName: true,
  },
  {
    id: 5,
    label: "Evidence",
    title: "The evidence trail",
    what: "Lists every self-healing record on the audit chain, then verifies the whole chain.",
    say:
      "Every step — what broke, what was proposed, who approved it, what changed — sits in the same tamper-evident chain as the loan decisions. An auditor can replay the entire incident.",
    look: "Eight records, two signed with your name — and the chain verifies.",
    button: "Show the evidence",
    running: "Reading the audit chain…",
  },
];

const EVENT_LABEL: Record<string, string> = {
  incident_opened: "Incident opened — diagnosis recorded",
  remediation_proposed: "Repair proposed, with shadow test",
  remediation_approved: "Repair approved",
  remediation_applied: "Repair applied",
  remediation_rejected: "Repair rejected",
  verified: "Verified on fresh traffic",
  verification_failed: "Verification failed",
  incident_closed: "Incident closed",
};

function StepResult({ id, start, result }: { id: number; start: HealingStart | null; result?: HealingStep }) {
  if (id === 0 && start) {
    return (
      <>
        <div className="mini-stats">
          <div>
            <span className="mini-value band-text-stable">{(start.severity ?? 0).toFixed(3)}</span>
            <span className="mini-label">drift (stable)</span>
          </div>
          <div>
            <span className="mini-value">{start.traffic.sent}</span>
            <span className="mini-label">healthy applications</span>
          </div>
          <div>
            <span className="mini-value">{start.tenant_id}</span>
            <span className="mini-label">fresh account</span>
          </div>
        </div>
        <DecisionResult d={start.decision} amount={250_000} />
      </>
    );
  }
  if (!result) return null;
  if (id === 5) {
    return (
      <div className="evidence">
        <ol className="evidence-list">
          {(result.events ?? []).map((e) => (
            <li key={e.seq} className={e.actor !== "custos" ? "is-human" : ""}>
              <span className="ev-seq">#{e.seq}</span>
              <span className="ev-name">{EVENT_LABEL[e.event] ?? e.event}</span>
              <span className="ev-actor">
                {e.actor === "custos" ? "Custos" : (
                  <>
                    <Icon name="user" /> {e.actor}
                  </>
                )}
              </span>
              <span className="ev-hash mono">{e.entry_hash.slice(0, 12)}…</span>
            </li>
          ))}
        </ol>
        <p className="muted small">
          Interleaved with {result.decisions_on_chain} loan decisions on the same chain.
        </p>
        {result.chain && <ChainResult chain={result.chain} />}
      </div>
    );
  }
  return (
    <>
      {result.traffic && (
        <>
          <div className="result-label">
            {id === 1 ? "What happened to the 200 applications on the dead feed" : "Applications on the repaired feed"}
          </div>
          <TrafficSummary step={result} />
        </>
      )}
      {result.incident && <IncidentCard incident={result.incident} busy />}
      {result.decision && (
        <>
          <div className="result-label">Our applicant, right now</div>
          <DecisionResult d={result.decision} amount={250_000} />
        </>
      )}
    </>
  );
}

export function Healing({ controlUrl, apiKey, onKey }: {
  controlUrl: string;
  apiKey: string;
  onKey: (key: string) => void;
}) {
  const demo = useMemo(() => new DemoClient(controlUrl), [controlUrl]);
  const queueClient = useMemo(() => (apiKey ? new ControlApiClient(controlUrl, apiKey) : null), [controlUrl, apiKey]);
  const [status, setStatus] = useState<HealingStatus | null>(null);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [start, setStart] = useState<HealingStart | null>(null);
  const [results, setResults] = useState<Record<number, HealingStep>>({});
  const [done, setDone] = useState<Set<number>>(new Set());
  const [viewing, setViewing] = useState(0);
  const [running, setRunning] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const approverState = useApprover();
  const [approver, setApprover] = approverState;
  const [signal, setSignal] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);

  const next = useMemo(() => STEPS.find((s) => !done.has(s.id))?.id ?? null, [done]);

  const poll = useCallback(async () => {
    try {
      setStatus(await demo.healingStatus());
      setUnavailable(null);
    } catch (caught) {
      setUnavailable(caught instanceof DemoUnavailable ? caught.message : String(caught));
    }
  }, [demo]);

  useEffect(() => {
    void poll();
    const timer = setInterval(() => void poll(), 4000);
    return () => clearInterval(timer);
  }, [poll]);

  const run = async (step: StepDef) => {
    if (step.needsName && !approver.trim()) {
      setError("Type your name in “Approving as” first — every approval records who made it.");
      return;
    }
    setRunning(step.id);
    setError(null);
    try {
      if (step.id === 0) {
        const started = await demo.healingStart();
        setStart(started);
        setResults({});
        setDone(new Set([0]));
        onKey(started.api_key);
      } else {
        const result = await demo.healingStep(step.id, step.needsName ? approver.trim() : undefined);
        setResults((r) => ({ ...r, [step.id]: result }));
        setDone((d) => new Set([...d, step.id]));
      }
      setViewing(step.id);
      setSignal((s) => s + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunning(null);
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
  const systemOk = !unavailable && status?.gateway;

  return (
    <div className="demo healing">
      <section className="demo-hero">
        <div className="eyebrow">Governed self-healing</div>
        <h1>
          When a model's data breaks, Custos proposes the fix. <span className="grad">A person decides.</span>
        </h1>
        <p className="lead">
          Self-healing systems that repair models on their own are a research direction. Custos takes the next
          step for production: it detects and diagnoses the problem, proposes a repair it can actually make,
          tests it on real recent decisions — and applies nothing until a named person approves. Every step lands
          on the same tamper-evident record as the decisions themselves.
        </p>
      </section>

      <section className="loop card" aria-label="The self-healing loop">
        {LOOP.map((stage, i) => (
          <div key={stage.name} className={`loop-stage ${stage.name === "Human approves" ? "is-human" : ""}`}>
            <div className="loop-num">{i + 1}</div>
            <div className="loop-name">{stage.name}</div>
            <div className="loop-body">{stage.body}</div>
          </div>
        ))}
      </section>

      <section className="playbook">
        {PLAYBOOK.map((p) => (
          <div className="card play" key={p.diagnosis}>
            <div className="play-diag">
              {p.diagnosis} <span className="muted">— {p.detail}</span>
            </div>
            <div className="play-row">
              <span className="play-tag tag-do">Proposes</span>
              <p>{p.repair}</p>
            </div>
            <div className="play-row">
              <span className="play-tag tag-dont">Refuses</span>
              <p>{p.refuses}</p>
            </div>
          </div>
        ))}
        <div className="card play play-contrast">
          <div className="play-diag">What Custos never does</div>
          <p>
            Retrain your model. It doesn't own it. A retrain is a <b>recorded request</b> to the model's owner, with
            the evidence attached — never something Custos pretends to have done.
          </p>
          <p className="muted small">
            Compare autonomous self-healing (Rauba et al., NeurIPS 2024): repairs without a human, and without a
            record of who decided.
          </p>
        </div>
      </section>

      <div className="section-head heal-demo-head">
        <div className="eyebrow">Guided run · about three minutes</div>
        <h2>A data feed breaks, live.</h2>
      </div>

      <section className="howto card">
        <div className="syscheck">
          <span className={`light ${systemOk ? "light-ok" : unavailable || status ? "light-bad" : "light-wait"}`} />
          {unavailable ? (
            <span>
              <b>Custos isn't reachable.</b> {unavailable} Run <code>./app.sh</code> in a terminal, then refresh.
            </span>
          ) : !status ? (
            <span>Checking the system…</span>
          ) : systemOk ? (
            <span><b>System ready.</b> Each step below drives the real gateway and control plane.</span>
          ) : (
            <span><b>The gateway is down.</b> Run <code>./app.sh</code>, then wait a few seconds.</span>
          )}
        </div>
      </section>

      <nav className="stepper" aria-label="Self-healing steps">
        {STEPS.map((s) => {
          const state = done.has(s.id) ? "done" : s.id === next ? "current" : "locked";
          return (
            <button
              key={s.id}
              className={`stepper-item is-${state} ${viewing === s.id ? "is-viewing" : ""}`}
              onClick={() => (state !== "locked" ? setViewing(s.id) : undefined)}
              disabled={state === "locked"}
            >
              <span className="stepper-dot">{state === "done" ? <Icon name="check" /> : s.id === 0 ? "▶" : s.id}</span>
              <span className="stepper-label">{s.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="heal-stage" ref={cardRef}>
        <article className={`step-card card ${isLocked ? "is-locked" : ""}`}>
          <div className="step-eyebrow">
            {step.id === 0 ? "Getting started" : `Step ${step.id} of ${STEPS.length - 1}`}
            {isDone && <span className="done-tag"><Icon name="check" /> Done</span>}
          </div>
          <h2 className="step-title">{step.title}</h2>
          <p className="step-what">{step.what}</p>

          <div className="say">
            <div className="say-head"><Icon name="mic" /> Say this to the audience</div>
            <p>“{step.say}”</p>
          </div>

          {!isDone && (
            <div className="step-actions">
              {isLocked ? (
                <div className="locked-note"><Icon name="lock" /> Finish the earlier steps first.</div>
              ) : running === step.id ? (
                <div className="running"><span className="spinner" /> {step.running}</div>
              ) : (
                <div className="heal-go">
                  {step.needsName && <ApproverField name={approver} onChange={setApprover} />}
                  <button className="btn btn-primary btn-xl" onClick={() => void run(step)} disabled={!systemOk || running !== null}>
                    {step.button}
                  </button>
                </div>
              )}
            </div>
          )}

          {error && running === null && !isDone && (
            <div className="error-box">
              <Icon name="alert" />
              <div>
                <b>That step didn't run.</b> {error}
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
              <div className="step-actions">
                {next !== null ? (
                  <button
                    className="btn btn-primary btn-xl"
                    onClick={() => {
                      setViewing(next);
                      cardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                    }}
                  >
                    Next step →
                  </button>
                ) : (
                  <div className="finish">
                    <div className="finish-title"><Icon name="spark" /> Self-healing demo complete</div>
                    <p className="muted">
                      The incident is in the queue below, resolved, with every decision and who made it.
                    </p>
                    <div className="finish-actions">
                      <button className="btn" onClick={restart}>Run it again</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </article>
      </div>

      <div className="section-head heal-demo-head">
        <div className="eyebrow">Live approval queue</div>
        <h2>Incidents for {queueClient ? "the connected account" : "your account"}.</h2>
      </div>
      <IncidentQueue client={queueClient} refreshSignal={signal} approver={approverState} />
    </div>
  );
}
