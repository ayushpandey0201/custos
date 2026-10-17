import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import "./design.css";

/* -----------------------------------------------------------------------------
 * Inside Custos — the system design page, prepared for the Phase-II review.
 *
 * Deliberately light-themed and self-contained: every diagram is inline SVG so
 * it stays sharp on a projector and needs nothing from the network. It is a
 * presentation copy and is meant to be removed after the review.
 * -------------------------------------------------------------------------- */

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "hld", label: "High-level design" },
  { id: "flow", label: "Life of a decision" },
  { id: "cascade", label: "Decision logic" },
  { id: "maths", label: "The maths" },
  { id: "lld", label: "Low-level design" },
  { id: "data", label: "Data model" },
  { id: "chain", label: "Audit chain" },
  { id: "healing", label: "Self-healing" },
  { id: "reliability", label: "Reliability & scale" },
  { id: "different", label: "How it's different" },
  { id: "ai", label: "Is Custos AI?" },
  { id: "onboard", label: "Onboarding plan" },
  { id: "domains", label: "Where it applies" },
  { id: "limits", label: "Limits" },
];

/* --- SVG building blocks ----------------------------------------------------- */

type Tone = "hot" | "cold" | "state" | "client" | "worker" | "ok" | "warn" | "bad" | "plain";

const TONES: Record<Tone, { fill: string; stroke: string; ink: string }> = {
  hot: { fill: "#eef4ff", stroke: "#8fb2f5", ink: "#1e3a8a" },
  cold: { fill: "#f4f0ff", stroke: "#b9a6f5", ink: "#4c1d95" },
  state: { fill: "#f6f8fb", stroke: "#c3ccda", ink: "#1e293b" },
  client: { fill: "#effaf3", stroke: "#86d3a2", ink: "#14532d" },
  worker: { fill: "#fff8eb", stroke: "#f2c46b", ink: "#78350f" },
  ok: { fill: "#ecfbf1", stroke: "#4ac27a", ink: "#14532d" },
  warn: { fill: "#fff6e6", stroke: "#e9a93a", ink: "#78350f" },
  bad: { fill: "#fff0f0", stroke: "#ef8a8a", ink: "#7f1d1d" },
  plain: { fill: "#ffffff", stroke: "#d5dbe6", ink: "#1e293b" },
};

function Box({
  x, y, w, h, title, lines = [], tone = "plain", bold = true,
}: {
  x: number; y: number; w: number; h: number; title: string; lines?: string[]; tone?: Tone; bold?: boolean;
}) {
  const t = TONES[tone];
  const total = 1 + lines.length;
  const lineH = 16;
  const top = y + h / 2 - ((total - 1) * lineH) / 2 + 5;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={12} fill={t.fill} stroke={t.stroke} strokeWidth={1.6} />
      <text x={x + w / 2} y={top} textAnchor="middle" className={bold ? "sv-title" : "sv-sub"} fill={t.ink}>
        {title}
      </text>
      {lines.map((line, i) => (
        <text key={i} x={x + w / 2} y={top + (i + 1) * lineH} textAnchor="middle" className="sv-sub">
          {line}
        </text>
      ))}
    </g>
  );
}

function Frame({ x, y, w, h, label, tone }: { x: number; y: number; w: number; h: number; label: string; tone: Tone }) {
  const t = TONES[tone];
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={18} fill={t.fill} fillOpacity={0.45} stroke={t.stroke}
        strokeWidth={1.4} strokeDasharray="6 5" />
      <text x={x + 16} y={y + 22} className="sv-frame" fill={t.ink}>{label}</text>
    </g>
  );
}

function Arrow({ d, label, lx, ly, dashed = false, color = "#64748b" }: {
  d: string; label?: string; lx?: number; ly?: number; dashed?: boolean; color?: string;
}) {
  return (
    <g>
      <path d={d} fill="none" stroke={color} strokeWidth={1.7} strokeDasharray={dashed ? "5 4" : undefined}
        markerEnd="url(#sv-arrow)" />
      {label && lx !== undefined && ly !== undefined && (
        <text x={lx} y={ly} textAnchor="middle" className="sv-edge">{label}</text>
      )}
    </g>
  );
}

function Defs() {
  return (
    <defs>
      <marker id="sv-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
      </marker>
    </defs>
  );
}

/* --- diagrams -------------------------------------------------------------- */

function HLD() {
  return (
    <svg viewBox="0 0 1120 640" className="sv" role="img" aria-label="High-level architecture of Custos">
      <Defs />
      {/* clients */}
      <Frame x={10} y={20} w={215} h={300} label="YOUR SYSTEMS" tone="client" />
      <Box x={28} y={58} w={180} h={58} title="Lending bot" lines={["Python SDK · @custos.guard"]} tone="client" />
      <Box x={28} y={132} w={180} h={58} title="AI refund agent" lines={["Python SDK · custos.gate"]} tone="client" />
      <Box x={28} y={206} w={180} h={58} title="Any service" lines={["REST · POST /v1/evaluate"]} tone="client" />
      <text x={117} y={290} textAnchor="middle" className="sv-note">If Custos is unreachable,</text>
      <text x={117} y={306} textAnchor="middle" className="sv-note">the SDK fails open or closed</text>

      {/* gateway */}
      <Frame x={250} y={20} w={510} h={300} label="GATEWAY · DATA PLANE · HOT PATH (p99 ≤ 50 ms)" tone="hot" />
      <Box x={270} y={52} w={110} h={52} title="Auth" lines={["hashed API key"]} tone="hot" />
      <Box x={398} y={52} w={130} h={52} title="Admission" lines={["≤ 8 in flight · else 503"]} tone="hot" />
      <Box x={546} y={52} w={196} h={52} title="Fan-out" lines={["concurrent · 20 ms per engine"]} tone="hot" />
      <Arrow d="M380 78 L396 78" />
      <Arrow d="M528 78 L544 78" />
      <Box x={270} y={132} w={150} h={58} title="Policy engine" lines={["parsed rules · veto"]} tone="plain" />
      <Box x={432} y={132} w={150} h={58} title="Drift engine" lines={["cached severity read"]} tone="plain" />
      <Box x={594} y={132} w={150} h={58} title="Risk engine" lines={["amount · velocity"]} tone="plain" />
      <path d="M644 104 L644 118 L345 118 L345 130" fill="none" stroke="#64748b" strokeWidth={1.5} markerEnd="url(#sv-arrow)" />
      <path d="M507 118 L507 130" fill="none" stroke="#64748b" strokeWidth={1.5} markerEnd="url(#sv-arrow)" />
      <path d="M669 118 L669 130" fill="none" stroke="#64748b" strokeWidth={1.5} markerEnd="url(#sv-arrow)" />
      <path d="M345 190 L345 203 M507 190 L507 203 M669 190 L669 203 M345 203 L669 203" fill="none" stroke="#64748b" strokeWidth={1.5} />
      <Arrow d="M345 203 L345 216" />
      <Box x={270} y={218} w={150} h={54} title="Fusion" lines={["weighted trust score"]} tone="hot" />
      <Box x={432} y={218} w={150} h={54} title="Decision cascade" lines={["8 ordered rules"]} tone="hot" />
      <Box x={594} y={218} w={150} h={54} title="Audit writer" lines={["one thread · hash chain"]} tone="hot" />
      <Arrow d="M420 245 L430 245" />
      <Arrow d="M582 245 L592 245" />
      <text x={505} y={300} textAnchor="middle" className="sv-note">
        → ALLOW / REVIEW / BLOCK, the reasons, and an audit id
      </text>

      {/* client ↔ gateway */}
      <Arrow d="M208 120 L268 78" label="evaluate" lx={238} ly={92} />
      <Arrow d="M268 262 L210 262" label="verdict" lx={238} ly={255} dashed />

      {/* state */}
      <Frame x={790} y={20} w={320} h={300} label="STATE" tone="state" />
      <Box x={810} y={52} w={280} h={80} title="Redis cache (TTL)" tone="state"
        lines={["tenant config · drift severity", "model registry · quarantines"]} />
      <Box x={810} y={148} w={280} h={128} title="PostgreSQL" tone="state"
        lines={["(SQLite on a laptop)", "tenants · models · baselines", "decisions · audit_entries (hash chain)", "drift_snapshots · incidents · remediations"]} />
      <Arrow d="M808 92 L746 92" label="cached reads" lx={777} ly={84} dashed />
      <Arrow d="M746 245 L808 245" label="append" lx={777} ly={237} />

      {/* control plane */}
      <Frame x={250} y={350} w={510} h={250} label="CONTROL PLANE · COLD PATH" tone="cold" />
      <Box x={270} y={385} w={150} h={58} title="Tenants & keys" lines={["key stored hashed"]} tone="cold" />
      <Box x={432} y={385} w={150} h={58} title="Models & baselines" lines={["register · reference data"]} tone="cold" />
      <Box x={594} y={385} w={150} h={58} title="Rules & config" lines={["parsed · weights"]} tone="cold" />
      <Box x={270} y={460} w={150} h={58} title="Audit" lines={["list · verify · export"]} tone="cold" />
      <Box x={432} y={460} w={150} h={58} title="Self-healing" lines={["diagnose · approve"]} tone="cold" />
      <Box x={594} y={460} w={150} h={58} title="Drift history" lines={["per-input attribution"]} tone="cold" />
      <text x={505} y={555} textAnchor="middle" className="sv-note">Slow, correct work lives here: verifying a whole chain,</text>
      <text x={505} y={572} textAnchor="middle" className="sv-note">validating a rule's grammar, replaying decisions in shadow.</text>
      <Arrow d="M760 400 L870 400 L870 324" label="read / write" lx={815} ly={393} />

      {/* worker */}
      <Box x={810} y={470} w={280} h={96} title="Drift worker (scheduled)" tone="worker"
        lines={["PSI + KS per input → severity", "then self-healing: detect & verify", "invalidates the cache entry"]} />
      <Arrow d="M1040 470 L1040 324" label="snapshots" lx={1078} ly={400} />

      {/* dashboard */}
      <Box x={20} y={400} w={200} h={110} title="Dashboard (React)" tone="client"
        lines={["guided demos · docs", "operator console", "approval queue"]} />
      <Arrow d="M220 455 L268 455" label="HTTPS" lx={244} ly={447} />

      {/* legend */}
      <g transform="translate(20, 612)">
        <rect width="14" height="14" rx="4" fill={TONES.hot.fill} stroke={TONES.hot.stroke} />
        <text x="20" y="12" className="sv-legend">hot path — every request</text>
        <rect x="220" width="14" height="14" rx="4" fill={TONES.cold.fill} stroke={TONES.cold.stroke} />
        <text x="240" y="12" className="sv-legend">cold path — operators and schedules</text>
        <rect x="490" width="14" height="14" rx="4" fill={TONES.worker.fill} stroke={TONES.worker.stroke} />
        <text x="510" y="12" className="sv-legend">offline statistics</text>
        <rect x="660" width="14" height="14" rx="4" fill={TONES.state.fill} stroke={TONES.state.stroke} />
        <text x="680" y="12" className="sv-legend">shared state</text>
      </g>
    </svg>
  );
}

function Sequence() {
  const lanes = [
    { x: 95, name: "Your service", sub: "SDK" },
    { x: 275, name: "Gateway", sub: "data plane" },
    { x: 445, name: "Policy", sub: "engine" },
    { x: 585, name: "Drift", sub: "engine" },
    { x: 725, name: "Risk", sub: "engine" },
    { x: 875, name: "Decision", sub: "fusion + cascade" },
    { x: 1030, name: "Audit chain", sub: "storage" },
  ];
  const msg = (from: number, to: number, y: number, label: string, dashed = false, lx?: number) => (
    <Arrow d={`M${from} ${y} L${to + (to > from ? -6 : 6)} ${y}`} label={label} lx={lx ?? (from + to) / 2} ly={y - 8} dashed={dashed} />
  );
  return (
    <svg viewBox="0 0 1120 500" className="sv" role="img" aria-label="Sequence of one evaluation request">
      <Defs />
      {lanes.map((l) => (
        <g key={l.name}>
          <rect x={l.x - 60} y={14} width={120} height={46} rx={11} fill="#ffffff" stroke="#c3ccda" strokeWidth={1.5} />
          <text x={l.x} y={34} textAnchor="middle" className="sv-title">{l.name}</text>
          <text x={l.x} y={50} textAnchor="middle" className="sv-sub">{l.sub}</text>
          <line x1={l.x} y1={60} x2={l.x} y2={488} stroke="#cfd6e2" strokeWidth={1.4} strokeDasharray="4 5" />
        </g>
      ))}
      {/* activation bars */}
      <rect x={269} y={92} width={12} height={350} rx={3} fill="#dbe7ff" stroke="#8fb2f5" />
      {[445, 585, 725].map((x) => (
        <rect key={x} x={x - 6} y={186} width={12} height={46} rx={3} fill="#eef1f6" stroke="#b5bfcf" />
      ))}
      <rect x={869} y={276} width={12} height={34} rx={3} fill="#dbe7ff" stroke="#8fb2f5" />
      <rect x={1024} y={340} width={12} height={34} rx={3} fill="#eef1f6" stroke="#b5bfcf" />

      {msg(95, 269, 96, "1  POST /v1/evaluate")}
      <text x={182} y={114} textAnchor="middle" className="sv-sub">model · action · features · context</text>
      <rect x={292} y={112} width={360} height={46} rx={9} fill="#f6f8fb" stroke="#d5dbe6" />
      <text x={304} y={131} className="sv-sub">2  auth (cached) · admission: ≤ 8 in flight</text>
      <text x={304} y={148} className="sv-sub">    full → 503 at once; the SDK applies fail-open/closed</text>
      {msg(281, 445, 190, "")}
      {msg(281, 585, 190, "")}
      {msg(281, 725, 190, "3  fan out concurrently · 20 ms each", false, 500)}
      {msg(445, 281, 232, "", true)}
      {msg(585, 281, 232, "", true)}
      {msg(725, 281, 232, "4  signals: score · veto · evidence", true, 500)}
      {msg(281, 875, 280, "5  fuse with tenant weights · check quarantines · 8-rule cascade", false, 578)}
      {msg(875, 281, 310, "ALLOW / REVIEW / BLOCK + reasons", true, 578)}
      {msg(281, 1030, 344, "6  append SHA-256(prev ‖ record) on the single writer thread", false, 655)}
      {msg(1030, 281, 374, "audit id (entry hash)", true, 655)}
      {msg(269, 95, 410, "7  verdict · trust · reasons · audit id", true)}
      <text x={281} y={468} className="sv-note">8  after replying: the feature vector is stored for the next drift recompute (never on the response path)</text>
      <rect x={760} y={386} width={340} height={52} rx={10} fill="#ecfbf1" stroke="#4ac27a" />
      <text x={930} y={407} textAnchor="middle" className="sv-title" fill="#14532d">p99 31 ms at 200 requests / s</text>
      <text x={930} y={425} textAnchor="middle" className="sv-sub">engines ≈ 1–2 ms each · budget 50 ms</text>
    </svg>
  );
}

function HealingMachine() {
  const states: { x: number; title: string; lines: string[]; tone: Tone }[] = [
    { x: 14, title: "Detect", lines: ["every drift", "recompute"], tone: "plain" },
    { x: 164, title: "Diagnose", lines: ["stuck · missing", "or a real shift"], tone: "plain" },
    { x: 314, title: "Propose", lines: ["quarantine ·", "rebaseline · retrain"], tone: "plain" },
    { x: 464, title: "Shadow test", lines: ["replay ≤ 500", "real decisions"], tone: "plain" },
  ];
  return (
    <svg viewBox="0 0 1120 330" className="sv" role="img" aria-label="Self-healing state machine">
      <Defs />
      {states.map((s, i) => (
        <g key={s.title}>
          <Box x={s.x} y={50} w={134} h={78} title={s.title} lines={s.lines} tone={s.tone} />
          {i < states.length - 1 && <Arrow d={`M${s.x + 134} 89 L${s.x + 162} 89`} />}
        </g>
      ))}
      <Arrow d="M598 89 L640 89" />
      {/* decision diamond */}
      <polygon points="712,30 790,89 712,148 634,89" fill="#fff6e6" stroke="#e9a93a" strokeWidth={2} />
      <text x={712} y={84} textAnchor="middle" className="sv-title" fill="#78350f">A named</text>
      <text x={712} y={101} textAnchor="middle" className="sv-title" fill="#78350f">person decides</text>
      <Arrow d="M790 89 L838 89" label="approve" lx={814} ly={80} />
      <Box x={840} y={50} w={120} h={78} title="Apply" lines={["next request", "sees it"]} tone="ok" />
      <Arrow d="M960 89 L988 89" />
      <Box x={990} y={50} w={120} h={78} title="Verify" lines={["fresh traffic", "only"]} tone="ok" />
      <Arrow d="M712 148 L712 196" label="reject" lx={740} ly={178} />
      <Box x={642} y={198} w={140} h={54} title="Rejected" lines={["recorded, no change"]} tone="bad" />
      <Arrow d="M1050 128 L1050 196" label="healthy" lx={1084} ly={168} />
      <Box x={990} y={198} w={120} h={54} title="Resolved" lines={["on the record"]} tone="ok" />
      <Arrow d="M1010 128 L930 196" label="not yet" lx={948} ly={160} />
      <Box x={824} y={198} w={150} h={54} title="Release / rollback" lines={["back to a person"]} tone="warn" />
      <path d="M899 252 L899 290 L560 290 L560 175 L660 120" fill="none" stroke="#e9a93a" strokeWidth={1.6} strokeDasharray="5 4" markerEnd="url(#sv-arrow)" />
      <text x={24} y={190} className="sv-note">Refused, by design:</text>
      <text x={24} y={207} className="sv-note">· re-baselining on a broken feed</text>
      <text x={24} y={224} className="sv-note">· re-baselining while the population still moves</text>
      <text x={24} y={241} className="sv-note">· approving a repair that failed its shadow test</text>
      <text x={24} y={258} className="sv-note">· retraining a model Custos doesn't own</text>
      <text x={14} y={20} className="sv-frame" fill="#1e3a8a">EVERY TRANSITION IS APPENDED TO THE SAME HASH CHAIN AS THE DECISIONS</text>
    </svg>
  );
}

function HashChain() {
  const blocks = [
    { seq: 41, what: "ALLOW · loan", h: "9f3c…a1" },
    { seq: 42, what: "REVIEW · drift floor", h: "47be…0c" },
    { seq: 43, what: "healing · approved by A. Rao", h: "c02d…9e" },
    { seq: 44, what: "BLOCK · policy veto", h: "e81a…33" },
  ];
  return (
    <svg viewBox="0 0 1120 210" className="sv" role="img" aria-label="Hash-chained audit log">
      <Defs />
      {blocks.map((b, i) => {
        const x = 20 + i * 275;
        const prev = i === 0 ? "…" : blocks[i - 1].h;
        return (
          <g key={b.seq}>
            <rect x={x} y={20} width={230} height={124} rx={14} fill={i === 1 ? "#fff0f0" : "#ffffff"} stroke={i === 1 ? "#ef8a8a" : "#c3ccda"} strokeWidth={1.6} />
            <text x={x + 16} y={44} className="sv-title">Entry #{b.seq}</text>
            <text x={x + 16} y={66} className="sv-mono">prev_hash  {prev}</text>
            <text x={x + 16} y={88} className="sv-sub">{b.what}</text>
            <line x1={x + 12} x2={x + 218} y1={102} y2={102} stroke="#e2e7ef" />
            <text x={x + 16} y={126} className="sv-mono" fill="#1e3a8a">entry_hash  {b.h}</text>
            {i < blocks.length - 1 && <Arrow d={`M${x + 230} 120 C ${x + 252} 120, ${x + 252} 62, ${x + 272} 62`} />}
          </g>
        );
      })}
      <text x={20} y={176} className="sv-note">entry_hash = SHA-256(prev_hash ‖ canonical JSON of the record). Each entry commits to the one before it.</text>
      <text x={20} y={198} className="sv-note" fill="#b91c1c">Edit #42 afterwards → its hash no longer matches, and every link after it breaks. GET /audit/verify names #42.</text>
    </svg>
  );
}

/* --- page pieces ------------------------------------------------------------- */

function Section({ id, eyebrow, title, lead, children }: {
  id: string; eyebrow: string; title: string; lead?: string; children: ReactNode;
}) {
  return (
    <section className="sd-section" id={id}>
      <div className="sd-eyebrow">{eyebrow}</div>
      <h2 className="sd-h2">{title}</h2>
      {lead && <p className="sd-lead">{lead}</p>}
      {children}
    </section>
  );
}

function Figure({ children, caption }: { children: ReactNode; caption: string }) {
  return (
    <figure className="sd-figure">
      {children}
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

const STATS = [
  { v: "≤ 50 ms", l: "p99 budget — 31 ms measured at 200 req/s" },
  { v: "0", l: "verdicts changed by overload" },
  { v: "397", l: "automated tests" },
  { v: "589,186", l: "real loans in a pre-registered study" },
  { v: "3 · 2", l: "live demos · domains" },
  { v: "0", l: "learned parameters in the decision path" },
];

const CASCADE = [
  { n: 1, cond: "any engine vetoes", out: "BLOCK" },
  { n: 2, cond: "trust < 0.30", out: "BLOCK" },
  { n: 3, cond: "model never registered", out: "REVIEW" },
  { n: 4, cond: "every engine degraded", out: "REVIEW" },
  { n: 5, cond: "an input is quarantined", out: "REVIEW" },
  { n: 6, cond: "drift is significant", out: "REVIEW" },
  { n: 7, cond: "trust < 0.60", out: "REVIEW" },
  { n: 8, cond: "otherwise", out: "ALLOW" },
];

const MODULES = [
  { path: "services/gateway", name: "Gateway", what: "Auth, admission gate, fan-out with per-engine timeouts, fusion, the decision cascade, the audit writer thread.", why: "One process owns the hot path; everything slow is elsewhere." },
  { path: "engines/policy", name: "Policy engine", what: "Tokeniser, recursive-descent parser and AST evaluator for tenant rules; veto on match.", why: "Rules are parsed, never eval'd — a rule can't become code execution." },
  { path: "engines/drift", name: "Drift engine + worker", what: "PSI and KS in pure Python; monotone severity roll-up; offline worker; cached hot-path read.", why: "Statistics are paid for on a schedule, not per request (ADR 0002)." },
  { path: "engines/risk", name: "Risk engine", what: "Robust amount z-score (median/MAD) and per-customer velocity over 60 s.", why: "Worst component wins; abstains rather than guesses without history." },
  { path: "services/healing", name: "Self-healing", what: "Diagnosis (stuck/missing/shift), proposals, shadow replay, approval state machine, verification.", why: "Repairs only its own gating; nothing applies without a named person (ADR 0006)." },
  { path: "services/control", name: "Control plane", what: "Tenants, models, baselines, rules, config, drift history, audit, the healing API, demo routes.", why: "Cold path: free to do slow, correct things." },
  { path: "shared/", name: "Shared contract", what: "ORM models, TTL cache (Redis or in-process), tenant config, model registry, quarantine lookup.", why: "Both planes agree on one schema and one set of cache keys." },
  { path: "sdk/python", name: "Python SDK", what: "@custos.guard decorator and custos.gate context manager; Blocked and ReviewRequired exceptions.", why: "Standard library only — it lives inside someone else's service." },
  { path: "dashboard/", name: "Dashboard", what: "React + TypeScript: guided demos, documentation, operator console, approval queue, page guides.", why: "The product's face for operators and reviewers." },
];

const TABLES = [
  { name: "tenants", cols: ["tenant_id", "api_key_hash", "config (weights, thresholds)"], note: "one per customer company" },
  { name: "models", cols: ["tenant_id · model_id", "baseline (reference sample)", "baseline_at"], note: "unregistered → REVIEW" },
  { name: "feature_samples", cols: ["tenant_id · model_id", "features", "created_at"], note: "the live window for drift" },
  { name: "drift_snapshots", cols: ["severity", "per_feature (psi, ks)", "computed_at"], note: "written by the worker, read by the gateway" },
  { name: "decisions", cols: ["decision · trust_score", "reasons · signals", "latency_ms"], note: "fast dashboard copy" },
  { name: "audit_entries", cols: ["seq · prev_hash", "entry_hash", "payload"], note: "the record of truth" },
  { name: "policy_rules", cols: ["rule_id", "condition", "action (veto)"], note: "grammar-checked on write" },
  { name: "incidents", cols: ["kind (break / shift)", "diagnosis", "status"], note: "one open per model per kind" },
  { name: "remediations", cols: ["action · params", "shadow result", "decided_by · undo"], note: "the repair and who approved it" },
];

const LAYERS = [
  { layer: "Policy rules", does: "Is this action allowed at all?", how: "Grammar parser + AST evaluation", learned: "No — written by people" },
  { layer: "Drift", does: "Has the model's input population moved?", how: "PSI + KS against a frozen reference sample", learned: "No — measured, not learned" },
  { layer: "Risk", does: "Is this one request unusual?", how: "Robust z-score (median/MAD), 60 s velocity", learned: "No — running statistics" },
  { layer: "Fusion + cascade", does: "One verdict, with reasons", how: "Weighted mean + 8 ordered rules", learned: "No — configured weights" },
  { layer: "Self-healing", does: "What broke, and what to do?", how: "Signature tests, hold-out test, decision replay", learned: "No — deterministic checks" },
  { layer: "Audit", does: "Prove what happened", how: "SHA-256 hash chain", learned: "No — cryptography" },
  { layer: "Research harness", does: "Does a gate actually help? (not in the product)", how: "Logistic regression (IRLS), Mahalanobis novelty", learned: "Yes — offline, pre-registered" },
];

const ONBOARD = [
  { when: "Day 1", title: "Connect", items: ["Create a tenant → an API key, shown once and stored hashed", "Register each model", "Upload a baseline from its validation data"] },
  { when: "Day 1", title: "Encode the business", items: ["Write rules as plain conditions (refund_ratio > 1 → veto)", "Choose weights per domain — an agent weighs risk, a credit model weighs drift", "Choose fail-open or fail-closed"] },
  { when: "Day 2", title: "Integrate", items: ["Wrap the consequential action: five lines with the SDK", "Route ReviewRequired to the team's existing review queue", "Blocked means the action never runs"] },
  { when: "Week 1", title: "Watch and tune", items: ["Read decisions, drift and reasons in the console", "Tune thresholds and weights — configuration, not code", "Verify the audit chain"] },
  { when: "Ongoing", title: "Operate", items: ["Scheduled drift + self-healing detection", "Approve or reject repairs in the incident queue", "Export the evidence for auditors and regulators"] },
];

const DOMAINS = [
  { d: "Lending", a: "approve a loan", s: "Demonstrated", tag: "EU AI Act high-risk" },
  { d: "AI agents", a: "refunds · any tool action", s: "Demonstrated", tag: "no code change" },
  { d: "Dynamic pricing", a: "publish a price", s: "By configuration", tag: "" },
  { d: "Medical triage", a: "route a patient low-priority", s: "By configuration", tag: "EU AI Act high-risk" },
  { d: "Hiring", a: "auto-reject a candidate", s: "By configuration", tag: "EU AI Act high-risk" },
  { d: "Insurance claims", a: "auto-pay a claim", s: "By configuration", tag: "" },
];

export function SystemDesign() {
  const [active, setActive] = useState("overview");

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
    <div className="sd">
      <header className="sd-hero" data-tour="design-hero">
        <div className="sd-eyebrow">Inside Custos · system design, HLD and LLD</div>
        <h1>
          Custos: the checkpoint between <span className="sd-grad">a model and the action it triggers.</span>
        </h1>
        <p className="sd-lead">
          Every consequential decision — a loan, a refund, a price, a triage call — passes through Custos before it
          happens. It answers ALLOW, REVIEW or BLOCK in milliseconds, explains why, keeps evidence nobody can quietly
          edit, and repairs its own gating when a data feed breaks — with a person's approval.
        </p>
        <div className="sd-stats" data-tour="design-stats">
          {STATS.map((s) => (
            <div className="sd-stat" key={s.l}>
              <div className="sd-stat-v">{s.v}</div>
              <div className="sd-stat-l">{s.l}</div>
            </div>
          ))}
        </div>
      </header>

      <div className="sd-layout">
        <nav className="sd-nav" data-tour="design-nav">
          {SECTIONS.map((s) => (
            <button key={s.id} className={active === s.id ? "is-active" : ""}
              onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" })}>
              {s.label}
            </button>
          ))}
        </nav>

        <div className="sd-body">
          <Section id="overview" eyebrow="01 · Overview" title="One question, asked before every action"
            lead="“Given everything I know about this model and this request right now — should this go ahead?”">
            <div className="sd-cards three">
              <div className="sd-card">
                <div className="sd-card-k">The problem</div>
                <p>Models are validated once and trusted forever. They don't crash when the world changes — they keep answering, confidently, and wrong. Checks happen quarterly; decisions happen every second.</p>
              </div>
              <div className="sd-card">
                <div className="sd-card-k">What Custos does</div>
                <p>Sits on the decision path. Fuses three signals — business policy, request risk and model drift — into one verdict with reasons, in a 50 ms budget, and records it in a tamper-evident chain.</p>
              </div>
              <div className="sd-card">
                <div className="sd-card-k">What it never does</div>
                <p>Train, serve or retrain your model. It decides, records and proposes repairs to its own gating; people approve. If it is unreachable, the caller's chosen fail-open or fail-closed policy applies.</p>
              </div>
            </div>
          </Section>

          <Section id="hld" eyebrow="02 · High-level design" title="Two planes, so nothing slow sits in the request path"
            lead="The gateway answers every request. Everything slow — statistics, chain verification, repairs — happens on the control plane or a schedule, and reaches the gateway only as a cached number.">
            <Figure caption="High-level architecture. Hot path in blue, cold path in violet, offline statistics in amber.">
              <HLD />
            </Figure>
            <div className="sd-cards three">
              <div className="sd-card"><div className="sd-card-k">Precomputed drift</div><p>PSI and KS run offline. On the hot path, drift is one cached read and a subtraction — the reason a full statistical check fits in milliseconds (ADR 0002).</p></div>
              <div className="sd-card"><div className="sd-card-k">Engines don't know each other</div><p>Each engine returns the same contract: a trust score, an optional veto, evidence. A fourth signal is a new file, not a refactor.</p></div>
              <div className="sd-card"><div className="sd-card-k">Degraded ≠ trusted</div><p>An engine with no answer is excluded from the score and named in the reasons — never quietly counted as “safe” (ADR 0004).</p></div>
            </div>
          </Section>

          <Section id="flow" eyebrow="03 · How it works" title="The life of one decision"
            lead="What happens between the SDK call and the verdict — eight steps, in about the time it takes a web page to start loading.">
            <Figure caption="Sequence of one POST /v1/evaluate. The three engines run at the same time, so the cost is the slowest one, not the sum.">
              <Sequence />
            </Figure>
          </Section>

          <Section id="cascade" eyebrow="04 · Decision logic" title="Eight rules, in order — the order is the specification"
            lead="Rules are checked before the score. A veto always wins; an unknown model is never auto-approved; a person's quarantine and the drift floor keep a model out of ALLOW however clean the other signals look.">
            <div className="sd-cascade">
              {CASCADE.map((r) => (
                <div key={r.n} className={`sd-rule out-${r.out.toLowerCase()}`}>
                  <span className="sd-rule-n">{r.n}</span>
                  <span className="sd-rule-c">{r.cond}</span>
                  <span className="sd-rule-o">{r.out}</span>
                </div>
              ))}
            </div>
          </Section>

          <Section id="maths" eyebrow="05 · The maths" title="Every number has a formula you can check by hand"
            lead="Custos measures; it does not learn. That is what makes every verdict explainable and every component testable against hand-computed values.">
            <div className="sd-cards two">
              <div className="sd-card sd-formula">
                <div className="sd-card-k">Population Stability Index</div>
                <code>PSI = Σ (aᵢ − eᵢ) · ln(aᵢ / eᵢ)</code>
                <p>Quantile buckets from the baseline. &lt; 0.10 stable · 0.10–0.25 moderate · &gt; 0.25 significant.</p>
              </div>
              <div className="sd-card sd-formula">
                <div className="sd-card-k">Kolmogorov–Smirnov</div>
                <code>KS = max |F_baseline(x) − F_live(x)|</code>
                <p>Bucket-free; catches shifts inside a PSI bucket. It can only raise a feature's severity, never lower it.</p>
              </div>
              <div className="sd-card sd-formula">
                <div className="sd-card-k">Model severity</div>
                <code>severity = 0.6 · max(sᵢ) + 0.4 · mean(sᵢ)</code>
                <p>One dead input can't hide among many stable ones, and one noisy input can't dominate. Monotone by construction.</p>
              </div>
              <div className="sd-card sd-formula">
                <div className="sd-card-k">Fusion</div>
                <code>trust = Σ wᵢ · scoreᵢ / Σ wᵢ  (live engines only)</code>
                <p>Drift score = 1 − severity. Risk score = 1 − worst component. A veto caps trust at 0.</p>
              </div>
              <div className="sd-card sd-formula">
                <div className="sd-card-k">Risk — amount</div>
                <code>z = (x − median) / max(1.4826 · MAD, 0.1 · median)</code>
                <p>Robust: the outliers it hunts can't drag “normal” around. Risk ramps from z = 3 to z = 10.</p>
              </div>
              <div className="sd-card sd-formula">
                <div className="sd-card-k">Admission — Little's law</div>
                <code>wait ≈ in-flight limit × time per write</code>
                <p>At a limit of 16 the 200 req/s p99 was 69 ms; at 8 it is 28–31 ms. Changes who waits, never a verdict.</p>
              </div>
            </div>
          </Section>

          <Section id="lld" eyebrow="06 · Low-level design" title="Every module, what it owns, and why it is built that way">
            <div className="sd-modules">
              {MODULES.map((m) => (
                <div className="sd-module" key={m.path}>
                  <div className="sd-module-head"><span className="sd-module-name">{m.name}</span><code>{m.path}</code></div>
                  <p>{m.what}</p>
                  <p className="sd-why">{m.why}</p>
                </div>
              ))}
            </div>
            <div className="sd-stack">
              {["Python 3", "FastAPI + Uvicorn", "SQLAlchemy + Alembic", "PostgreSQL / SQLite", "Redis", "Celery beat", "React + TypeScript + Vite", "stdlib-only SDK", "Docker Compose"].map((t) => (
                <span key={t}>{t}</span>
              ))}
            </div>
          </Section>

          <Section id="data" eyebrow="07 · Data model" title="Nine tables, every one scoped by tenant"
            lead="Every query filters on tenant_id first. Raw customer features never enter the audit log — only verdicts, scores and evidence.">
            <div className="sd-tables">
              {TABLES.map((t) => (
                <div className="sd-table" key={t.name}>
                  <div className="sd-table-name">{t.name}</div>
                  <ul>{t.cols.map((c) => <li key={c}>{c}</li>)}</ul>
                  <div className="sd-table-note">{t.note}</div>
                </div>
              ))}
            </div>
          </Section>

          <Section id="chain" eyebrow="08 · Evidence" title="A record nobody can quietly edit"
            lead="Tamper-evident, not tamper-proof: anyone with database access can change a row — what they can't do is hide it.">
            <Figure caption="Each entry commits to its predecessor. Decisions and self-healing events share one chain per tenant. (Hash values and names are illustrative.)">
              <HashChain />
            </Figure>
          </Section>

          <Section id="healing" eyebrow="09 · Governed self-healing" title="Custos proposes the repair. A person decides."
            lead="A broken data feed and a real population shift both look like “drift” — but need opposite repairs. Custos tells them apart, tests a repair on real decisions, and applies nothing without a named approver.">
            <Figure caption="The self-healing state machine. The amber diamond is the point of the design.">
              <HealingMachine />
            </Figure>
          </Section>

          <Section id="reliability" eyebrow="10 · Reliability, scale and security" title="Built to be trusted on the request path">
            <div className="sd-cards three">
              <div className="sd-card"><div className="sd-card-k">Overload is refused, not queued</div><p>Past 8 in-flight requests the gateway answers 503 at once. Before this, overload flipped up to 985 verdicts per run; now none.</p></div>
              <div className="sd-card"><div className="sd-card-k">Fail-open, loudly</div><p>If Custos can't answer, the caller proceeds flagged failed_open — or stops, if the tenant chose fail-closed. A guard that takes production down gets removed.</p></div>
              <div className="sd-card"><div className="sd-card-k">Race-safe evidence</div><p>Audit appends take a per-tenant Postgres advisory lock; 0 entries lost from 2 to 48 concurrent writers.</p></div>
              <div className="sd-card"><div className="sd-card-k">Security</div><p>API keys stored as SHA-256 only. Rules parsed by a grammar, never executed. Every table scoped by tenant. No customer data in the audit log.</p></div>
              <div className="sd-card"><div className="sd-card-k">Scale-out path</div><p>One process saturates near 300 req/s. More gateway workers behind Postgres and Redis — the lock and the cache are already shared-state ready.</p></div>
              <div className="sd-card"><div className="sd-card-k">Measured honestly</div><p>An open-loop load harness corrected for coordinated omission — it found three defects a one-request-at-a-time test never could.</p></div>
            </div>
          </Section>

          <Section id="different" eyebrow="11 · How Custos is different" title="Monitoring reports. Guardrails filter text. Custos decides."
            lead="The categories next door are crowded. Custos sits where they don't: on the decision itself, at the moment it happens, with a human checkpoint and evidence.">
            <div className="sd-compare">
              <div className="sd-col">
                <div className="sd-col-h">Model monitoring</div>
                <ul><li>After the fact — minutes to weeks</li><li>Can't stop anything; raises an alert</li><li>Charts and logs</li></ul>
              </div>
              <div className="sd-col">
                <div className="sd-col-h">Content guardrails</div>
                <ul><li>Filters the text of one prompt</li><li>Toxicity, personal data, jailbreaks</li><li>Doesn't see the business decision</li></ul>
              </div>
              <div className="sd-col is-custos">
                <div className="sd-col-h">Custos</div>
                <ul><li>Before every action, in ≤ 50 ms</li><li>ALLOW / REVIEW / BLOCK with reasons</li><li>Hash-chained evidence; governed repairs</li></ul>
              </div>
            </div>
            <div className="sd-impact">
              <div className="sd-impact-card"><div className="sd-impact-v">$304M</div><p>Zillow's one-quarter write-down when its pricing model kept acting as the market moved. The gap Custos closes: weeks of automated decisions on a drifted model.</p></div>
              <div className="sd-impact-card"><div className="sd-impact-v">200 / 200</div><p>loans a model still approved on a dead credit-score feed. Once a person approves the quarantine Custos proposes, every decision is held — with the exact cause named.</p></div>
              <div className="sd-impact-card"><div className="sd-impact-v">#7 · #9</div><p>A runaway AI agent refunding one customer twelve times: held for review at the 7th, blocked from the 9th. Nobody wrote a rule for loops.</p></div>
              <div className="sd-impact-card"><div className="sd-impact-v">1 record</div><p>Edit any past verdict and verification names the exact record that was touched. Evidence an auditor can actually rely on.</p></div>
            </div>
          </Section>

          <Section id="ai" eyebrow="12 · Defending the design" title="Is Custos AI? Deliberately — not in the decision path."
            lead="Custos is an AI-governance system: it guards machine-learning models and AI agents. Its own decision path contains no learned parameters, by design. Here is every layer, and why.">
            <div className="sd-layers">
              <div className="sd-layer sd-layer-head"><span>Layer</span><span>Question it answers</span><span>Technique</span><span>Learned?</span></div>
              {LAYERS.map((l) => (
                <div className={`sd-layer ${l.learned.startsWith("Yes") ? "is-research" : ""}`} key={l.layer}>
                  <span className="sd-layer-name">{l.layer}</span>
                  <span>{l.does}</span>
                  <span>{l.how}</span>
                  <span className={`sd-learned ${l.learned.startsWith("Yes") ? "yes" : "no"}`}>{l.learned}</span>
                </div>
              ))}
            </div>
            <div className="sd-defence">
              <div className="sd-q">
                <div className="sd-q-h">“Who guards the guard?”</div>
                <p>A learned guard would drift too — and need its own monitor, and that monitor another. Custos stops the regress: same input, same verdict, a reason in words, and every component tested against hand-computed values.</p>
              </div>
              <div className="sd-q">
                <div className="sd-q-h">“Does it guard against other AI drifting?”</div>
                <p>Yes — any model, treated as a black box: gradient boosting, a neural network, an LLM agent. It watches what goes in (drift, broken feeds), what is being done (amounts, bursts, forbidden actions), and records what came out.</p>
              </div>
              <div className="sd-q">
                <div className="sd-q-h">“Does Custos itself drift?”</div>
                <p>No — it has nothing learned to drift. Its baselines are explicit, versioned reference samples; changing one is a proposal a person approves, undoable, on the audit chain.</p>
              </div>
              <div className="sd-q">
                <div className="sd-q-h">“Then where is the AI?”</div>
                <p>In the systems it governs — and in the research. Our pre-registered study found the model's own risk ranking caught 2.1× more defaults than random review, while drift alone didn't beat random. A learned signal enters the product only after that kind of evaluation.</p>
              </div>
              <div className="sd-q">
                <div className="sd-q-h">“So is it MLOps?”</div>
                <p>The runtime half of it: monitoring, governance and control of models in production — plus governed repair. Training pipelines are the other half; Custos hands them a recorded retrain request with the evidence.</p>
              </div>
              <div className="sd-q">
                <div className="sd-q-h">“Why should a regulator trust it?”</div>
                <p>The EU AI Act asks high-risk systems — credit, hiring, emergency triage — for human oversight and automatic record-keeping. REVIEW verdicts, named approvals and a verifiable chain are exactly that.</p>
              </div>
            </div>
          </Section>

          <Section id="onboard" eyebrow="13 · Onboarding plan" title="From first call to production in about a week"
            lead="Onboarding is configuration and five lines of code — no model changes and no retraining. Custos can run inside the customer's own infrastructure (Docker Compose), so decision data need not leave it.">
            <div className="sd-timeline">
              {ONBOARD.map((o, i) => (
                <div className="sd-step" key={o.title}>
                  <div className="sd-step-dot">{i + 1}</div>
                  <div className="sd-step-when">{o.when}</div>
                  <div className="sd-step-title">{o.title}</div>
                  <ul>{o.items.map((it) => <li key={it}>{it}</li>)}</ul>
                </div>
              ))}
            </div>
            <pre className="sd-code">{`import custos
custos.configure(base_url=GATEWAY, api_key=KEY)

@custos.guard(model_id="refund-agent-v1", action="issue_refund", features="request")
def issue_refund(*, request):
    ...   # runs only on ALLOW — REVIEW and BLOCK raise, so nothing slips through`}</pre>
            <div className="sd-gtm">
              <div className="sd-card-k">Going to market — the plan, and its risks</div>
              <div className="sd-gtm-row">
                <div><b>1 · Beachhead: AI agents that act.</b> Agents are being handed tools that move money; little sits between “decided” and “done”.</div>
                <div><b>2 · Regulated decisions.</b> Credit, hiring and triage need human oversight and records under the EU AI Act.</div>
                <div><b>3 · The control plane for automated decisions.</b> One buyer — the owner of risk — across every model.</div>
              </div>
              <p className="sd-risk">
                <b>Honest risks:</b> larger platforms can add a guardrail feature, and horizontal infrastructure is hard to
                sell before a specific buyer. The defence is owning the approval workflow and the evidence — and first
                validating the beachhead with ten risk and compliance teams.
              </p>
            </div>
          </Section>

          <Section id="domains" eyebrow="14 · Where it applies" title="Any model whose output triggers an action"
            lead="A new domain is configuration — inputs, context, rules, weights. Two are demonstrated; the rest are stated, not claimed.">
            <div className="sd-domains">
              {DOMAINS.map((d) => (
                <div className={`sd-domain ${d.s === "Demonstrated" ? "is-demo" : ""}`} key={d.d}>
                  <div className="sd-domain-name">{d.d}</div>
                  <div className="sd-domain-a">gates: {d.a}</div>
                  <div className="sd-domain-tags">
                    <span className={d.s === "Demonstrated" ? "tag-demo" : "tag-cfg"}>{d.s}</span>
                    {d.tag && <span className="tag-reg">{d.tag}</span>}
                  </div>
                </div>
              ))}
            </div>
            <p className="sd-note">Not a fit: microsecond trading (the budget is 50 ms), filtering generated text, and anything with no discrete action to hold.</p>
          </Section>

          <Section id="limits" eyebrow="15 · Limits, stated plainly" title="What Custos does not do yet">
            <ul className="sd-limits">
              <li>Drift gating did not beat random review on real loans; the gate is being rebuilt around risk-ranked review.</li>
              <li>One field dataset so far; a second is needed before any general claim.</li>
              <li>Input drift only — not concept drift, because real outcomes arrive months later.</li>
              <li>Load measured on one machine with SQLite; one process saturates near 300 req/s.</li>
              <li>Self-healing recognises two fault signatures (stuck, missing); approvers are named, not authenticated.</li>
              <li>The AI-agent demo uses a simulated agent and synthetic traffic.</li>
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
