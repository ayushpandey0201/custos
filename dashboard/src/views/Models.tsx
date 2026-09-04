// Registered models + status.

import { useState } from "react";
import type { ControlApiClient, ModelSummary } from "../api/client";
import { Empty, Panel, relativeTime } from "../components/primitives";

export function Models({
  client,
  models,
  selected,
  onSelect,
  onChanged,
}: {
  client: ControlApiClient;
  models: ModelSummary[];
  selected: string | null;
  onSelect: (modelId: string) => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function recompute(modelId: string) {
    setBusy(modelId);
    setMessage(null);
    try {
      const result = await client.recompute(modelId);
      setMessage(
        result.computed
          ? `${modelId}: severity ${result.severity?.toFixed(3)}`
          : `${modelId}: ${result.detail}`,
      );
      onChanged();
    } catch (error) {
      setMessage(String(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel title="Models">
      {models.length === 0 ? (
        <Empty>No models registered. Traffic for an unknown model routes to REVIEW.</Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Version</th>
              <th>Baseline</th>
              <th>Registered</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr
                key={model.model_id}
                onClick={() => onSelect(model.model_id)}
                className={model.model_id === selected ? "row-selected" : "row-clickable"}
              >
                <td>
                  <strong>{model.model_id}</strong>
                  {model.name && <div className="muted">{model.name}</div>}
                </td>
                <td>{model.version}</td>
                <td>
                  {model.has_baseline ? (
                    <span className="muted">
                      {model.baseline_features} features · {relativeTime(model.baseline_at)}
                    </span>
                  ) : (
                    // Without a baseline the drift engine has nothing to compare
                    // against and reports degraded (ADR 0004) — worth flagging.
                    <span className="badge badge-moderate">none</span>
                  )}
                </td>
                <td className="muted">{relativeTime(model.registered_at)}</td>
                <td>
                  <button
                    disabled={busy === model.model_id}
                    onClick={(event) => {
                      event.stopPropagation();
                      void recompute(model.model_id);
                    }}
                  >
                    {busy === model.model_id ? "…" : "Recompute drift"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {message && <p className="muted note">{message}</p>}
    </Panel>
  );
}
