// Shared UI primitives.
//
// Kept here so that "what a REVIEW looks like" is decided once. A decision
// badge that is amber in one view and grey in another quietly teaches an
// operator to distrust the whole screen.

import type { ReactNode } from "react";
import type { DecisionValue, DriftBand } from "../api/client";

export function DecisionBadge({ decision }: { decision: DecisionValue }) {
  return <span className={`badge badge-${decision.toLowerCase()}`}>{decision}</span>;
}

export function BandBadge({ band }: { band: DriftBand }) {
  return <span className={`badge badge-${band}`}>{band}</span>;
}

/** Horizontal severity bar in [0,1]. Colour tracks the band thresholds. */
export function SeverityBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const band: DriftBand = value < 1 / 3 ? "stable" : value < 2 / 3 ? "moderate" : "significant";
  return (
    <div className="bar" title={`severity ${value.toFixed(3)}`}>
      <div className={`bar-fill bar-${band}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Sparkline over a severity history. Plain SVG — a chart library would be
 *  more dependency than this one shape is worth. */
export function Sparkline({ points, width = 220, height = 44 }: {
  points: number[];
  width?: number;
  height?: number;
}) {
  if (points.length === 0) return <span className="muted">no history</span>;
  if (points.length === 1) points = [points[0], points[0]];

  const step = width / (points.length - 1);
  const path = points
    .map((v, i) => `${i === 0 ? "M" : "L"} ${i * step} ${height - Math.min(1, Math.max(0, v)) * height}`)
    .join(" ");

  return (
    <svg width={width} height={height} className="sparkline" role="img" aria-label="drift severity over time">
      {/* Band guides at the 0.33 / 0.66 thresholds, so a line's height is readable. */}
      <line x1={0} x2={width} y1={height * (2 / 3)} y2={height * (2 / 3)} className="guide" />
      <line x1={0} x2={width} y1={height * (1 / 3)} y2={height * (1 / 3)} className="guide" />
      <path d={path} fill="none" className="spark-line" />
    </svg>
  );
}

export function Panel({ title, actions, children }: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {actions}
      </header>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="muted empty">{children}</p>;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
