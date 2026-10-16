// Client for the guided-demo endpoints (control plane, demo mode only).
//
// No API key: the demo creates its own tenant and hands the key back, so a
// first-time presenter never has to copy one from a terminal.

import type { DecisionValue, DriftBand } from "./client";

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

export class DemoUnavailable extends Error {}

export class DemoClient {
  constructor(private baseUrl: string) {}

  private async call<T>(path: string, method: "GET" | "POST" = "GET"): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, { method });
    } catch {
      throw new DemoUnavailable("Custos is not running.");
    }
    if (response.status === 404 && path === "/demo/status") {
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
}
