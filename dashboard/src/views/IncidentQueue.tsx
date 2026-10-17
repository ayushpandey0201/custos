import { useCallback, useEffect, useState } from "react";
import { ApiError, type ControlApiClient, type Incident, type Remediation, type RemediationAction } from "../api/client";
import { Icon } from "./GuidedDemo";

/* -----------------------------------------------------------------------------
 * The approval queue for governed self-healing.
 *
 * Everything a reviewer needs to decide is on the card: what broke, what
 * Custos proposes, what it deliberately did *not* propose and why, and the
 * shadow test — how many real recent decisions the repair would have changed.
 * Nothing is applied until someone types their name and approves.
 * -------------------------------------------------------------------------- */

const APPROVER_KEY = "custos.approver";

export const ACTION_LABEL: Record<RemediationAction, string> = {
  quarantine_input: "Quarantine the broken input",
  release_input: "Release the quarantine",
  rebaseline: "Accept the new population as the reference",
  rollback_baseline: "Roll back to the previous reference",
  request_retrain: "Ask the model owner to retrain",
};

const STATUS_LABEL: Record<string, string> = {
  proposed: "awaiting a decision",
  approved: "approved",
  applied: "applied",
  rejected: "rejected",
  superseded: "superseded",
  released: "released",
  rolled_back: "rolled back",
  failed_verification: "failed verification",
};

const INPUT_LABEL: Record<string, string> = {
  income: "Annual income",
  utilisation: "Credit utilisation",
  bureau_score: "Credit score",
  months_employed: "Months employed",
};

export function KindBadge({ kind }: { kind: Incident["kind"] }) {
  return kind === "pipeline_break" ? (
    <span className="heal-kind kind-break">Broken data feed</span>
  ) : (
    <span className="heal-kind kind-shift">Population shift</span>
  );
}

function when(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function ShadowEvidence({ r }: { r: Remediation }) {
  const transitions = Object.entries(r.shadow.impact?.transitions ?? {});
  return (
    <div className={`shadow ${r.shadow.passed ? "shadow-ok" : "shadow-bad"}`}>
      <div className="shadow-head">
        <Icon name="flask" />
        Shadow test {r.shadow.passed ? "passed" : "failed — cannot be approved"}
      </div>
      <p className="shadow-summary">{r.shadow.summary}</p>
      {transitions.length > 0 && (
        <div className="shadow-transitions">
          {transitions.map(([t, n]) => (
            <span key={t} className="transition">
              <b>{n}</b> {t.replace("→", " → ")}
            </span>
          ))}
        </div>
      )}
      <ul className="shadow-checks">
        {r.shadow.checks.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
    </div>
  );
}

export function RemediationCard({
  r,
  busy,
  onDecide,
  onRetest,
}: {
  r: Remediation;
  busy: boolean;
  onDecide?: (r: Remediation, verdict: "approve" | "reject") => void;
  onRetest?: (r: Remediation) => void;
}) {
  const proposed = r.status === "proposed";
  return (
    <div className={`remedy remedy-${r.status}`}>
      <div className="remedy-head">
        <span className="remedy-action">
          <Icon name="wrench" /> {ACTION_LABEL[r.action] ?? r.action}
        </span>
        <span className={`remedy-status status-${r.status}`}>{STATUS_LABEL[r.status] ?? r.status}</span>
      </div>
      <p className="remedy-why">{r.rationale}</p>
      <ShadowEvidence r={r} />
      {r.decided_by && (
        <div className="remedy-signed">
          <Icon name="user" /> {r.status === "rejected" ? "Rejected" : "Approved"} by <b>{r.decided_by}</b>
          {r.decided_at && <span className="muted"> at {when(r.decided_at)}</span>}
          {r.decision_note && <span className="muted"> — “{r.decision_note}”</span>}
        </div>
      )}
      {proposed && onDecide && (
        <div className="remedy-actions">
          <button
            className="btn btn-primary"
            disabled={busy || !r.shadow.passed}
            title={r.shadow.passed ? "Apply this repair" : "Failed its shadow test"}
            onClick={() => onDecide(r, "approve")}
          >
            Approve and apply
          </button>
          <button className="btn" disabled={busy} onClick={() => onDecide(r, "reject")}>
            Reject
          </button>
          {onRetest && (
            <button className="btn btn-ghost" disabled={busy} onClick={() => onRetest(r)}>
              Re-run shadow test
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function IncidentCard({
  incident,
  busy,
  onDecide,
  onRetest,
  onVerify,
  onClose,
}: {
  incident: Incident;
  busy: boolean;
  onDecide?: (r: Remediation, verdict: "approve" | "reject") => void;
  onRetest?: (r: Remediation) => void;
  onVerify?: (i: Incident) => void;
  onClose?: (i: Incident) => void;
}) {
  const unhealthy = incident.diagnosis.inputs.filter((i) => i.status !== "ok");
  return (
    <article className={`incident card incident-${incident.status}`}>
      <header className="incident-head">
        <div>
          <KindBadge kind={incident.kind} />
          <span className={`incident-state state-${incident.status}`}>
            {incident.status === "open" ? "Open" : "Resolved"}
          </span>
        </div>
        <span className="muted small">
          Incident #{incident.id} · <code>{incident.model_id}</code> · opened {when(incident.opened_at)}
          {incident.resolved_at && ` · resolved ${when(incident.resolved_at)}`}
        </span>
      </header>
      <h3 className="incident-summary">{incident.summary}</h3>

      {unhealthy.length > 0 && (
        <div className="diag">
          <div className="result-label">Diagnosis — last {incident.diagnosis.window} requests</div>
          {unhealthy.map((i) => (
            <div className="diag-row" key={i.name}>
              <span className="diag-name">{INPUT_LABEL[i.name] ?? i.name}</span>
              <span className={`diag-status diag-${i.status}`}>{i.status}</span>
              <span className="diag-detail">{i.detail}</span>
            </div>
          ))}
        </div>
      )}

      {incident.diagnosis.withheld?.length > 0 && (
        <div className="withheld">
          <Icon name="lock" />
          <div>
            <b>Deliberately not proposed:</b>{" "}
            {incident.diagnosis.withheld.map((w) => `${ACTION_LABEL[w.action as RemediationAction] ?? w.action} — ${w.why}.`).join(" ")}
          </div>
        </div>
      )}

      <div className="remedies">
        {incident.remediations.map((r) => (
          <RemediationCard key={r.id} r={r} busy={busy} onDecide={onDecide} onRetest={onRetest} />
        ))}
      </div>

      {incident.status === "open" && (onVerify || onClose) && (
        <div className="incident-actions">
          {onVerify && (
            <button className="btn btn-ghost" disabled={busy} onClick={() => onVerify(incident)}>
              Verify on current traffic
            </button>
          )}
          {onClose && (
            <button className="btn btn-ghost" disabled={busy} onClick={() => onClose(incident)}>
              Close without a repair
            </button>
          )}
        </div>
      )}
    </article>
  );
}

export function useApprover(): [string, (name: string) => void] {
  const [name, setName] = useState(() => localStorage.getItem(APPROVER_KEY) ?? "");
  const update = (value: string) => {
    setName(value);
    localStorage.setItem(APPROVER_KEY, value);
  };
  return [name, update];
}

export function ApproverField({ name, onChange }: { name: string; onChange: (v: string) => void }) {
  return (
    <label className="approver">
      <span>
        <Icon name="user" /> Approving as
      </span>
      <input
        value={name}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Type your name"
        maxLength={128}
      />
      <span className="muted small">Recorded on the audit chain with every decision you make.</span>
    </label>
  );
}

/** Live queue for one tenant, polling while open.
 *
 * ``approver`` can be lifted to the parent so a page with its own name field
 * (the guided demo) shares one value with the queue. */
export function IncidentQueue({
  client,
  refreshSignal = 0,
  approver: liftedApprover,
}: {
  client: ControlApiClient | null;
  refreshSignal?: number;
  approver?: [string, (name: string) => void];
}) {
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ownApprover = useApprover();
  const [approver, setApprover] = liftedApprover ?? ownApprover;
  const [filter, setFilter] = useState<"open" | "all">("open");

  const load = useCallback(async () => {
    if (!client) return;
    try {
      setIncidents(await client.incidents(filter === "open" ? "open" : undefined));
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setIncidents([]);
        setError(
          "The saved API key no longer works — usually because the demo data was rebuilt with ./app.sh --restart. Run the guided demo, or reconnect in the console.",
        );
        return;
      }
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [client, filter]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load, refreshSignal]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (caught) {
      const text = caught instanceof Error ? caught.message : String(caught);
      try {
        setError(JSON.parse(text).detail ?? text);
      } catch {
        setError(text);
      }
    } finally {
      setBusy(false);
    }
  };

  const needName = () => {
    if (approver.trim()) return false;
    setError("Type your name first — every decision on a repair records who made it.");
    return true;
  };

  if (!client) {
    return (
      <div className="card heal-empty">
        <p className="muted">
          Connect a tenant in the <a href="#/console">console</a> — or run the guided demo above, which connects
          one automatically — to see its incident queue.
        </p>
      </div>
    );
  }

  return (
    <div className="queue">
      <div className="queue-bar">
        <ApproverField name={approver} onChange={setApprover} />
        <div className="queue-filter">
          <button className={filter === "open" ? "btn btn-on" : "btn"} onClick={() => setFilter("open")}>
            Open
          </button>
          <button className={filter === "all" ? "btn btn-on" : "btn"} onClick={() => setFilter("all")}>
            All
          </button>
        </div>
      </div>
      {error && (
        <div className="error-box">
          <Icon name="alert" />
          <div>{error}</div>
        </div>
      )}
      {incidents === null ? (
        <p className="muted">Loading…</p>
      ) : incidents.length === 0 ? (
        <div className="card heal-empty">
          <Icon name="check" />
          <p>
            {filter === "open" ? "No open incidents." : "No incidents yet."} Custos checks for broken feeds and
            population shifts every time drift is recomputed.
          </p>
        </div>
      ) : (
        incidents.map((incident) => (
          <IncidentCard
            key={incident.id}
            incident={incident}
            busy={busy}
            onDecide={(r, verdict) => {
              if (needName()) return;
              void act(() => client.decideRemediation(r.id, verdict, approver.trim()));
            }}
            onRetest={(r) => void act(() => client.retestRemediation(r.id))}
            onVerify={(i) => void act(() => client.verifyIncident(i.id))}
            onClose={(i) => {
              if (needName()) return;
              void act(() => client.closeIncident(i.id, approver.trim(), "closed from the console"));
            }}
          />
        ))
      )}
    </div>
  );
}
