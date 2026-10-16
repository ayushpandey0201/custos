// Recent ALLOW / BLOCK / REVIEW stream.

import type { DecisionRow } from "../api/client";
import { DecisionBadge, Empty, Explain, Panel, relativeTime } from "../components/primitives";

export function Decisions({ decisions }: { decisions: DecisionRow[] }) {
  const counts = decisions.reduce<Record<string, number>>((acc, row) => {
    acc[row.decision] = (acc[row.decision] ?? 0) + 1;
    return acc;
  }, {});

  // p99 is the number the latency budget is written against, so it is the one
  // shown — a mean would hide exactly the tail this system promises to bound.
  const latencies = decisions.map((d) => d.latency_ms).sort((a, b) => a - b);
  const p99 = latencies.length ? latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * 0.99))] : 0;

  return (
    <Panel
      title="Recent decisions"
      actions={
        <span className="muted">
          {decisions.length} shown · p99 {p99.toFixed(1)} ms
        </span>
      }
    >
      <Explain
        what="Every request Custos has judged, newest first, with the verdict it returned and how long it took."
        why="This is the system doing its job, live. The response time matters as much as the verdict: Custos sits in front of real traffic, so if it were slow it would slow down everything behind it."
      />
      {decisions.length === 0 ? (
        <Empty>No decisions yet. Send traffic through the gateway.</Empty>
      ) : (
        <>
          <div className="counts">
            {(["ALLOW", "REVIEW", "BLOCK"] as const).map((decision) => (
              <div key={decision} className="stat">
                <div className="stat-value">{counts[decision] ?? 0}</div>
                <div className="stat-label">
                  <DecisionBadge decision={decision} />
                </div>
              </div>
            ))}
          </div>

          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Model</th>
                <th>Action</th>
                <th>Decision</th>
                <th>Trust</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((row) => (
                <tr key={row.id}>
                  <td className="muted">{relativeTime(row.created_at)}</td>
                  <td>{row.model_id}</td>
                  <td className="muted">{row.action}</td>
                  <td>
                    <DecisionBadge decision={row.decision} />
                  </td>
                  <td className="numeric">{row.trust_score.toFixed(2)}</td>
                  <td className="muted reason">{row.reasons[0] ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Panel>
  );
}
