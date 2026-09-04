// Per-model severity + per-feature breakdown.
//
// The per-feature table is the point of this view. A single severity number
// tells an operator that something moved; only the breakdown tells them which
// input moved, which is what decides whether this is a real population shift
// or a broken upstream feed.

import type { DriftHistory } from "../api/client";
import { BandBadge, Empty, Panel, SeverityBar, Sparkline, relativeTime } from "../components/primitives";

export function DriftMonitor({ modelId, drift }: { modelId: string | null; drift: DriftHistory | null }) {
  if (!modelId) {
    return (
      <Panel title="Drift monitor">
        <Empty>Select a model to see its drift breakdown.</Empty>
      </Panel>
    );
  }

  if (!drift?.current) {
    return (
      <Panel title={`Drift monitor · ${modelId}`}>
        <Empty>{drift?.detail ?? "No drift snapshots computed yet."}</Empty>
      </Panel>
    );
  }

  const current = drift.current;
  const features = Object.entries(current.per_feature).sort((a, b) => b[1].severity - a[1].severity);

  return (
    <Panel
      title={`Drift monitor · ${modelId}`}
      actions={<span className="muted">computed {relativeTime(current.computed_at)}</span>}
    >
      <div className="drift-summary">
        <div className="stat">
          <div className="stat-value">{current.severity.toFixed(3)}</div>
          <div className="stat-label">
            model severity <BandBadge band={current.band} />
          </div>
        </div>
        <div className="stat">
          <div className="stat-value">{current.sample_size.toLocaleString()}</div>
          <div className="stat-label">observations in window</div>
        </div>
        <div className="stat">
          <Sparkline points={drift.history.map((point) => point.severity)} />
          <div className="stat-label">severity over time</div>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Feature</th>
            <th>PSI</th>
            <th>KS</th>
            <th>Severity</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {features.map(([name, stats]) => (
            <tr key={name}>
              <td>
                <strong>{name}</strong>
              </td>
              <td className="numeric">{stats.psi.toFixed(3)}</td>
              <td className="numeric">{stats.ks.toFixed(3)}</td>
              <td>
                <BandBadge band={stats.band} />
              </td>
              <td className="bar-cell">
                <SeverityBar value={stats.severity} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="muted note">
        PSI bands: &lt; 0.10 stable · 0.10–0.25 moderate · &gt; 0.25 significant.
      </p>
    </Panel>
  );
}
