// Searchable audit + evidence export + chain verify.

import { Fragment, useState } from "react";
import type { AuditEntry, ChainVerification, ControlApiClient } from "../api/client";
import { DecisionBadge, Empty, Explain, Panel, Term, relativeTime } from "../components/primitives";
import type { DecisionValue } from "../api/client";

export function AuditLog({
  client,
  entries,
  filter,
  onFilter,
}: {
  client: ControlApiClient;
  entries: AuditEntry[];
  filter: string;
  onFilter: (decision: string) => void;
}) {
  const [verification, setVerification] = useState<ChainVerification | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  async function verify() {
    setVerifying(true);
    try {
      setVerification(await client.verifyChain());
    } catch (error) {
      setVerification({ valid: false, entries: 0, broken_at: null, detail: String(error) });
    } finally {
      setVerifying(false);
    }
  }

  return (
    <Panel
      title="Audit chain"
      actions={
        <div className="actions">
          <select value={filter} onChange={(event) => onFilter(event.target.value)}>
            <option value="">all decisions</option>
            <option value="ALLOW">ALLOW</option>
            <option value="REVIEW">REVIEW</option>
            <option value="BLOCK">BLOCK</option>
          </select>
          <button onClick={() => void verify()} disabled={verifying}>
            {verifying ? "Verifying…" : "Verify chain"}
          </button>
          <a className="button" href={client.exportUrl()} download>
            Export evidence
          </a>
        </div>
      }
    >
      <Explain
        what="A permanent record of every decision, where each entry is mathematically locked to the one before it."
        why="An ordinary log can be edited by anyone with database access, so it proves nothing. Here, changing any past record breaks the lock on every record after it. Press Verify chain to check the whole history — if someone altered an entry, it says exactly which one."
      />
      {verification && (
        <div className={verification.valid ? "verdict verdict-ok" : "verdict verdict-bad"}>
          <strong>{verification.valid ? "Chain verified" : "Chain broken"}</strong>
          <span>{verification.detail}</span>
          {verification.broken_at !== null && <span>first break at entry #{verification.broken_at}</span>}
        </div>
      )}

      {entries.length === 0 ? (
        <Empty>No audit entries.</Empty>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>When</th>
              <th>Model</th>
              <th>Decision</th>
              <th>Entry hash</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const payload = entry.payload as {
                model_id?: string;
                decision?: DecisionValue;
                trust_score?: number;
                reasons?: string[];
              };
              return (
                <Fragment key={entry.seq}>
                  <tr
                    className="row-clickable"
                    onClick={() => setExpanded(expanded === entry.seq ? null : entry.seq)}
                  >
                    <td className="numeric">{entry.seq}</td>
                    <td className="muted">{relativeTime(entry.created_at)}</td>
                    <td>{payload.model_id ?? "—"}</td>
                    <td>{payload.decision ? <DecisionBadge decision={payload.decision} /> : "—"}</td>
                    {/* Truncated: the full hash is in the expanded payload and
                        in the export. A 64-char column would push out the
                        fields an operator actually scans. */}
                    <td className="mono muted">{entry.entry_hash.slice(0, 16)}…</td>
                  </tr>
                  {expanded === entry.seq && (
                    <tr>
                      <td colSpan={5}>
                        <pre className="payload">{JSON.stringify(entry.payload, null, 2)}</pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
