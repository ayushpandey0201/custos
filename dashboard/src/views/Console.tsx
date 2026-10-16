import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ControlApiClient,
  type AuditEntry,
  type DecisionRow,
  type DriftHistory,
  type ModelSummary,
  type TenantConfig,
} from "../api/client";
import { ExplainContext } from "../components/primitives";
import { AuditLog } from "./AuditLog";
import { Decisions } from "./Decisions";
import { DriftMonitor } from "./DriftMonitor";
import { Models } from "./Models";

/** The operator console: a thin window onto the control plane.
 *
 * It holds no credentials of its own — the tenant's API key is either pasted
 * here or handed over by the guided demo, and it stays in this browser. */
export function Console({ controlUrl, apiKey, setApiKey }: {
  controlUrl: string;
  apiKey: string;
  setApiKey: (key: string) => void;
}) {
  const [keyDraft, setKeyDraft] = useState(apiKey);
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [drift, setDrift] = useState<DriftHistory | null>(null);
  const [decisions, setDecisions] = useState<DecisionRow[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [auditFilter, setAuditFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Default on: the first person to open this screen is usually being shown
  // the system, not operating it.
  const [explain, setExplain] = useState(true);

  const client = useMemo(() => new ControlApiClient(controlUrl, apiKey), [controlUrl, apiKey]);

  useEffect(() => setKeyDraft(apiKey), [apiKey]);

  const refresh = useCallback(async () => {
    if (!apiKey) return;
    try {
      const [modelList, decisionRows, auditPage, tenantConfig] = await Promise.all([
        client.listModels(),
        client.recentDecisions(50),
        client.auditEntries({ limit: 50, decision: auditFilter || undefined }),
        client.config(),
      ]);
      setModels(modelList);
      setDecisions(decisionRows);
      setAudit(auditPage.entries);
      setConfig(tenantConfig);
      setError(null);
      setSelected((current) => current ?? modelList[0]?.model_id ?? null);
    } catch (caught) {
      setError(
        String(caught).includes("401")
          ? "This API key is not valid any more — probably the demo was restarted. Paste the new key, or run the guided demo again."
          : String(caught),
      );
    }
  }, [apiKey, auditFilter, client]);

  useEffect(() => {
    void refresh();
    // Polling rather than websockets: the control plane is deliberately cold,
    // and a 5s refresh is well inside how fast any of this data changes.
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!selected || !apiKey) return;
    client
      .driftHistory(selected)
      .then(setDrift)
      .catch(() => setDrift(null));
  }, [selected, apiKey, client, models]);

  if (!apiKey) {
    return (
      <div className="console-gate card">
        <div className="eyebrow">Operator console</div>
        <h2>Connect a tenant</h2>
        <p className="muted">
          The easiest way in is the <a href="#/demo">live demo</a> — it connects this console
          automatically. Or paste a tenant API key (printed by <code>./app.sh</code> and saved in{" "}
          <code>.run/api-key.txt</code>).
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setApiKey(keyDraft.trim());
          }}
        >
          <input
            value={keyDraft}
            onChange={(event) => setKeyDraft(event.target.value)}
            placeholder="custos_…"
            autoFocus
          />
          <button type="submit" className="btn btn-primary">Connect</button>
        </form>
        <p className="muted small">Control plane: {controlUrl}</p>
      </div>
    );
  }

  return (
    <div className="console">
      <header className="console-head">
        <div>
          <div className="eyebrow">Operator console</div>
          <h2>{config ? config.tenant_id : "…"}</h2>
          {config && (
            <span className="muted small">
              engines {config.enabled_engines.join(", ")} · block &lt; {config.thresholds.block} ·
              review &lt; {config.thresholds.review} · {config.fail_open ? "fail-open" : "fail-closed"}
            </span>
          )}
        </div>
        <div className="actions">
          <button
            className={explain ? "btn btn-on" : "btn"}
            onClick={() => setExplain((on) => !on)}
            title="Show a plain-English description on every panel"
          >
            {explain ? "Explanations: on" : "Explanations: off"}
          </button>
          <button className="btn" onClick={() => setApiKey("")}>
            Disconnect
          </button>
        </div>
      </header>

      {error && <div className="verdict verdict-bad">{error}</div>}

      <ExplainContext.Provider value={explain}>
        <main className="console-grid">
          <Models
            client={client}
            models={models}
            selected={selected}
            onSelect={setSelected}
            onChanged={() => void refresh()}
          />
          <DriftMonitor modelId={selected} drift={drift} />
          <Decisions decisions={decisions} />
          <AuditLog client={client} entries={audit} filter={auditFilter} onFilter={setAuditFilter} />
        </main>
      </ExplainContext.Provider>
    </div>
  );
}
