import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ControlApiClient,
  type AuditEntry,
  type DecisionRow,
  type DriftHistory,
  type ModelSummary,
  type TenantConfig,
} from "./api/client";
import { AuditLog } from "./views/AuditLog";
import { Decisions } from "./views/Decisions";
import { DriftMonitor } from "./views/DriftMonitor";
import { Models } from "./views/Models";

const CONTROL_URL = import.meta.env.VITE_CONTROL_URL ?? "http://localhost:8001";
const STORAGE_KEY = "custos.apiKey";

export function App() {
  // The dashboard is a thin window onto the control plane and holds no
  // credentials of its own — the operator pastes the tenant's API key and it
  // stays in this browser.
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(STORAGE_KEY) ?? "");
  const [keyDraft, setKeyDraft] = useState(apiKey);

  const [models, setModels] = useState<ModelSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [drift, setDrift] = useState<DriftHistory | null>(null);
  const [decisions, setDecisions] = useState<DecisionRow[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [auditFilter, setAuditFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const client = useMemo(() => new ControlApiClient(CONTROL_URL, apiKey), [apiKey]);

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

      // Default to the first model so the drift view is never empty on load.
      setSelected((current) => current ?? modelList[0]?.model_id ?? null);
    } catch (caught) {
      setError(String(caught));
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
      <div className="gate">
        <h1>Custos</h1>
        <p className="muted">Runtime trust layer for AI agents and models.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            localStorage.setItem(STORAGE_KEY, keyDraft.trim());
            setApiKey(keyDraft.trim());
          }}
        >
          <input
            value={keyDraft}
            onChange={(event) => setKeyDraft(event.target.value)}
            placeholder="tenant API key"
            autoFocus
          />
          <button type="submit">Connect</button>
        </form>
        <p className="muted small">Control plane: {CONTROL_URL}</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Custos</h1>
          <span className="muted">
            {config ? `${config.tenant_id} · engines ${config.enabled_engines.join(", ")}` : "…"}
          </span>
        </div>
        <div className="actions">
          {config && (
            <span className="muted small">
              block &lt; {config.thresholds.block} · review &lt; {config.thresholds.review} ·{" "}
              {config.fail_open ? "fail-open" : "fail-closed"}
            </span>
          )}
          <button
            onClick={() => {
              localStorage.removeItem(STORAGE_KEY);
              setApiKey("");
            }}
          >
            Disconnect
          </button>
        </div>
      </header>

      {error && <div className="verdict verdict-bad">{error}</div>}

      <main>
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
    </div>
  );
}
