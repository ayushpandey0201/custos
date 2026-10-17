// Client for the guided-demo endpoints (control plane, demo mode only).
//
// No API key: the demo creates its own tenant and hands the key back, so a
// first-time presenter never has to copy one from a terminal.

import type { DecisionValue, DriftBand, Incident } from "./client";

export type BotVerdict = "APPROVED" | "DENIED" | "HELD_FOR_REVIEW" | "BLOCKED";

export interface DemoDecision {
  bot: BotVerdict;
  custos: DecisionValue;
  trust_score: number | null;
  reason: string;
  default_probability: number;
  trace_id: string;
}

export interface ChainCheck {
  valid: boolean;
  entries: number;
  broken_at: number | null;
  detail: string;
}

export interface Traffic {
  sent: number;
  verdicts: Partial<Record<DecisionValue, number>>;
}

export interface DemoStart {
  tenant_id: string;
  api_key: string;
  application: Record<string, number>;
  model_id: string;
}

export interface DemoStep {
  step: number;
  decision?: DemoDecision;
  amount?: number;
  baseline_size?: number;
  traffic?: Traffic;
  severity?: number | null;
  severity_before?: number | null;
  severity_after?: number | null;
  band_after?: DriftBand | null;
  features?: { feature: string; psi: number; band: DriftBand; severity: number }[];
  held_for_review?: number;
  chain?: ChainCheck;
  edited_seq?: number;
  changed?: { from: string; to: string };
}

export interface DemoStatus {
  gateway: boolean;
  control: boolean;
  run: { tenant_id: string; done: number[] } | null;
}

export interface HealingStart {
  tenant_id: string;
  api_key: string;
  model_id: string;
  traffic: Traffic;
  severity: number | null;
  decision: DemoDecision;
}

export interface HealingEvent {
  seq: number;
  entry_hash: string;
  event: string;
  action: string | null;
  actor: string;
  created_at: string;
}

export interface HealingStep {
  step: number;
  stuck_value?: number;
  traffic?: Traffic;
  healing?: { incident_id: number | null; kind: string | null; new: boolean; verification: string | null };
  incident?: Incident;
  decision?: DemoDecision;
  events?: HealingEvent[];
  decisions_on_chain?: number;
  chain?: ChainCheck;
}

export interface HealingStatus {
  gateway: boolean;
  run: { tenant_id: string; done: number[] } | null;
}

export interface AgentDecision {
  custos: DecisionValue;
  trust_score: number;
  reason: string;
  agent: string;
  amount: number;
  customer: string;
  requests_last_minute: number | null;
}

export interface AgentStart {
  tenant_id: string;
  api_key: string;
  model_id: string;
  weights: Record<string, number>;
  rules: { rule_id: string; condition: string; description: string }[];
  traffic: Traffic;
  severity: number | null;
}

export interface AgentStep {
  step: number;
  decision?: AgentDecision;
  order_value?: number;
  attempts?: AgentDecision[];
  verdicts?: Partial<Record<DecisionValue, number>>;
  traffic?: Traffic;
  checks?: { after: number; severity: number | null; incident: number | null }[];
  severity_after?: number | null;
  band_after?: DriftBand | null;
  features?: { feature: string; psi: number; band: DriftBand; severity: number }[];
  healing?: { incident_id: number | null; kind: string | null; new: boolean } | null;
  incidents_open?: number;
  chain?: ChainCheck;
}

export class DemoUnavailable extends Error {}

export class DemoClient {
  constructor(private baseUrl: string) {}

  private async call<T>(path: string, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: body === undefined ? undefined : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new DemoUnavailable("Custos is not running.");
    }
    if (response.status === 404 && path.endsWith("/status")) {
      throw new DemoUnavailable("Custos is running without demo mode.");
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        detail = (await response.json()).detail ?? detail;
      } catch {
        /* keep the status text */
      }
      throw new Error(detail);
    }
    return (await response.json()) as T;
  }

  status() {
    return this.call<DemoStatus>("/demo/status");
  }

  start() {
    return this.call<DemoStart>("/demo/start", "POST");
  }

  act(step: number) {
    return this.call<DemoStep>(`/demo/act/${step}`, "POST");
  }

  tamper() {
    return this.call<DemoStep>("/demo/tamper", "POST");
  }

  agentStatus() {
    return this.call<HealingStatus>("/demo/agent/status");
  }

  agentStart() {
    return this.call<AgentStart>("/demo/agent/start", "POST");
  }

  agentStep(step: number) {
    return this.call<AgentStep>(`/demo/agent/step/${step}`, "POST");
  }

  healingStatus() {
    return this.call<HealingStatus>("/demo/healing/status");
  }

  healingStart() {
    return this.call<HealingStart>("/demo/healing/start", "POST");
  }

  healingStep(step: number, approver?: string) {
    return this.call<HealingStep>(`/demo/healing/step/${step}`, "POST", approver ? { approver } : {});
  }
}
