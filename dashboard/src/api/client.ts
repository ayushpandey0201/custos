// Typed HTTP client for the control API.
//
// Every response shape the dashboard depends on is declared here rather than
// inferred at each call site, so a contract change in the Python layer surfaces
// as a TypeScript error in one file instead of as `undefined` in a table cell.

export type DecisionValue = "ALLOW" | "REVIEW" | "BLOCK";
export type DriftBand = "stable" | "moderate" | "significant";

export interface ModelSummary {
  model_id: string;
  name: string;
  version: string;
  status: string;
  has_baseline: boolean;
  baseline_features: number;
  baseline_at: string | null;
  registered_at: string;
}

export interface FeatureDrift {
  psi: number;
  ks: number;
  severity: number;
  band: DriftBand;
}

export interface DriftPoint {
  severity: number;
  band: DriftBand;
  sample_size: number;
  computed_at: string | null;
}

export interface DriftDetail extends DriftPoint {
  per_feature: Record<string, FeatureDrift>;
  top_features: { feature: string; severity: number }[];
}

export interface DriftHistory {
  model_id: string;
  current: DriftDetail | null;
  history: DriftPoint[];
  detail?: string;
}

export interface DecisionRow {
  id: number;
  model_id: string;
  decision: DecisionValue;
  trust_score: number;
  action: string;
  trace_id: string;
  reasons: string[];
  latency_ms: number;
  created_at: string | null;
}

export interface AuditEntry {
  seq: number;
  entry_hash: string;
  prev_hash: string;
  trace_id: string;
  created_at: string | null;
  payload: Record<string, unknown>;
}

export interface ChainVerification {
  valid: boolean;
  entries: number;
  broken_at: number | null;
  detail: string;
}

export interface TenantConfig {
  tenant_id: string;
  enabled_engines: string[];
  weights: Record<string, number>;
  thresholds: Record<string, number>;
  fail_open: boolean;
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

export class ControlApiClient {
  constructor(
    private baseUrl: string,
    private apiKey: string,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.apiKey,
        ...(init.headers ?? {}),
      },
    });

    if (!response.ok) {
      // Surface the server's own message where there is one — "block threshold
      // must not exceed review" is far more useful to an operator than "400".
      const body = await response.text();
      throw new ApiError(response.status, body || response.statusText);
    }
    return (await response.json()) as T;
  }

  listModels() {
    return this.request<ModelSummary[]>("/models");
  }

  driftHistory(modelId: string) {
    return this.request<DriftHistory>(`/models/${encodeURIComponent(modelId)}/drift`);
  }

  recompute(modelId: string) {
    return this.request<{ computed: boolean; severity?: number; detail?: string }>(
      `/models/${encodeURIComponent(modelId)}/recompute`,
      { method: "POST" },
    );
  }

  recentDecisions(limit = 50) {
    return this.request<DecisionRow[]>(`/audit/decisions?limit=${limit}`);
  }

  auditEntries(params: { limit?: number; decision?: string; model_id?: string } = {}) {
    const query = new URLSearchParams();
    query.set("limit", String(params.limit ?? 50));
    if (params.decision) query.set("decision", params.decision);
    if (params.model_id) query.set("model_id", params.model_id);
    return this.request<{ entries: AuditEntry[] }>(`/audit?${query}`);
  }

  verifyChain() {
    return this.request<ChainVerification>("/audit/verify");
  }

  config() {
    return this.request<TenantConfig>("/config");
  }

  /** Absolute URL for the evidence export, for use as a download link. */
  exportUrl() {
    return `${this.baseUrl}/audit/export`;
  }
}
