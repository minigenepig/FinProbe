import type {
  DashboardSummary,
  InvestigationEvent,
  InvestigationSnapshot,
  PageResult,
} from "../types";
import type { ErpResource } from "../erpCatalog";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || "";

async function parse<T>(resp: Response): Promise<T> {
  const data = await resp.json();
  if (!resp.ok || data.ok === false) {
    const message = data?.error?.message || `HTTP ${resp.status}`;
    const err = new Error(message) as Error & { code?: string };
    err.code = data?.error?.code;
    throw err;
  }
  return data as T;
}

export async function getHealth() {
  const resp = await fetch(`${API_BASE}/v1/health`);
  return resp.json();
}

export async function createInvestigation(question: string, wantReport?: boolean) {
  const body: Record<string, unknown> = { question };
  if (typeof wantReport === "boolean") body.wantReport = wantReport;
  const resp = await fetch(`${API_BASE}/v1/investigations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await parse<{ ok: true; investigation: InvestigationSnapshot }>(resp);
  return data.investigation;
}

export async function listInvestigations() {
  const resp = await fetch(`${API_BASE}/v1/investigations`);
  const data = await parse<{ ok: true; investigations: Array<Record<string, string | null>> }>(resp);
  return data.investigations;
}

export async function getInvestigation(id: string) {
  const resp = await fetch(`${API_BASE}/v1/investigations/${id}`);
  const data = await parse<{ ok: true; investigation: InvestigationSnapshot }>(resp);
  return data.investigation;
}

export async function postMessage(id: string, content: string) {
  const resp = await fetch(`${API_BASE}/v1/investigations/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  const data = await parse<{ ok: true; investigation: InvestigationSnapshot }>(resp);
  return data.investigation;
}

export async function cancelInvestigation(id: string) {
  const resp = await fetch(`${API_BASE}/v1/investigations/${id}/cancel`, { method: "POST" });
  const data = await parse<{ ok: true; investigation: InvestigationSnapshot }>(resp);
  return data.investigation;
}

export async function getReport(id: string) {
  const resp = await fetch(`${API_BASE}/v1/investigations/${id}/report`);
  return parse<{ ok: true; report: Record<string, unknown>; markdown: string; draft: boolean }>(resp);
}

function asRows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is Record<string, unknown> => {
    if (!row || typeof row !== "object" || Array.isArray(row)) return false;
    return Object.values(row).some((item) => item != null && item !== "");
  });
}

export async function listErp(resource: ErpResource, params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  const resp = await fetch(`${API_BASE}/v1/erp/${resource}?${q.toString()}`);
  const payload = await parse<PageResult>(resp);
  const nested = payload.data as unknown;
  const rows = Array.isArray(nested)
    ? asRows(nested)
    : asRows((nested as { data?: unknown } | null)?.data);
  return { ...payload, data: rows };
}

export async function getErp(resource: ErpResource, id: string) {
  const resp = await fetch(`${API_BASE}/v1/erp/${resource}/${encodeURIComponent(id)}`);
  const data = await parse<{ ok: true; resource: string; data: Record<string, unknown> }>(resp);
  return data.data;
}

export async function getDashboard() {
  const resp = await fetch(`${API_BASE}/v1/dashboard/summary`);
  return parse<DashboardSummary>(resp);
}

export function openEventStream(
  id: string,
  afterSeq: number,
  onEvent: (event: InvestigationEvent) => void,
  onError: (err: Event) => void,
): EventSource {
  const url = `${API_BASE}/v1/investigations/${id}/events?afterSeq=${afterSeq}`;
  const es = new EventSource(url);
  const types = [
    "status.changed",
    "route.decided",
    "agent.started",
    "agent.thought",
    "agent.completed",
    "tool.started",
    "tool.completed",
    "envelope.upserted",
    "evidence.completed",
    "report.completed",
    "message.assistant",
    "message.clarify",
    "heartbeat",
    "error",
  ];
  for (const type of types) {
    es.addEventListener(type, (raw) => {
      const msg = raw as MessageEvent<string>;
      try {
        onEvent(JSON.parse(msg.data) as InvestigationEvent);
      } catch {
        /* ignore */
      }
    });
  }
  es.onerror = onError;
  return es;
}