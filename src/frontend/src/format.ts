import type { InvestigationEvent, InvestigationSnapshot } from "./types";

export const STATUS_LABEL: Record<string, string> = {
  created: "已创建",
  routing: "路由中",
  locating: "定位实体",
  running: "调查中",
  awaiting_user: "等待澄清",
  reviewing: "证据审核",
  follow_up: "补查中",
  reporting: "生成报告",
  completed: "完成",
  failed: "失败",
  cancelled: "已取消",
};

const COMPANY_RE = /启衡精密制造有限公司|启衡精密制造/g;

export function stripCompany(text: string | null | undefined): string {
  if (!text) return "";
  return text.replace(COMPANY_RE, "本公司");
}

export function money(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value == null || value === "" ? "—" : String(value);
  return n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function levelClass(level?: string | null): string {
  if (level === "高风险") return "level-high";
  if (level === "中风险") return "level-mid";
  if (level === "低风险") return "level-low";
  return "level-gap";
}

export function riskWordClass(level?: string | null): string {
  if (level === "高风险") return "level-high";
  if (level === "中风险" || level === "低风险") return "level-strong";
  return "level-gap";
}

export function heatClass(level?: string | null): string {
  if (level === "高风险") return "heat-high";
  if (level === "中风险") return "heat-mid";
  if (level === "低风险") return "heat-low";
  return "heat-gap";
}

export function formatRiskMessage(snap: InvestigationSnapshot): string {
  const lines: string[] = [];
  if (snap.overallRiskLevel) lines.push(`总体风险：${snap.overallRiskLevel}`);
  for (const env of snap.envelopes || []) {
    for (const finding of env.findings || []) {
      lines.push(`- ${finding.riskType}：${finding.riskLevel}`);
      if (finding.rootCause) lines.push(`  根因：${stripCompany(finding.rootCause)}`);
      if (finding.recommendation) lines.push(`  建议：${stripCompany(finding.recommendation)}`);
    }
    if (env.answer && !(env.findings || []).length) lines.push(stripCompany(env.answer));
  }
  if (!lines.length && snap.answer) return stripCompany(snap.answer);
  return stripCompany(lines.join("\n"));
}

export function eventTitle(ev: InvestigationEvent): string {
  const p = ev.payload || {};
  switch (ev.type) {
    case "status.changed":
      return `状态 → ${STATUS_LABEL[String(p.status)] || p.status}`;
    case "route.decided":
      return `路由 ${p.mode}/${p.scope}`;
    case "agent.started":
      return `${p.agent} 开始`;
    case "agent.thought":
      return `思考 ${p.thought || ""}`;
    case "agent.completed":
      return p.degraded ? `${p.agent} 完成（证据不足）` : `${p.agent} 完成`;
    case "tool.started":
      return `行动 ${p.label || p.tool}${p.target ? `（${p.target}）` : ""}`;
    case "tool.completed":
      return `观察 ${p.observation || (p.ok === false ? p.error : p.totalCount === 0 ? "未检索到记录" : "已返回结果")}`;
    case "envelope.upserted":
      return `信封 ${p.skill || ""}`;
    case "evidence.completed":
      return `证据审核 ready=${p.readyForReport}`;
    case "report.completed":
      return `报告 ${p.reportId || ""}`;
    case "message.clarify":
      return "需要澄清";
    case "message.assistant":
      return "助手回复";
    case "error":
      return p.isolated ? `${p.agent || "领域"} 降级为证据不足` : `错误 ${p.code || ""}`;
    default:
      return ev.type;
  }
}

export function displayCell(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : money(value);
  if (typeof value === "object") return JSON.stringify(value);
  return stripCompany(String(value));
}

export function docPath(id: string): string | null {
  if (!id) return null;
  if (id.startsWith("VEN-")) return `/erp/vendors/${id}`;
  if (id.startsWith("PO-")) return `/erp/purchase-orders/${id}`;
  if (id.startsWith("GR-")) return `/erp/goods-receipts/${id}`;
  if (id.startsWith("INV-")) return `/erp/invoices/${id}`;
  if (id.startsWith("PAY-")) return `/erp/payments/${id}`;
  if (id.startsWith("APR-") || id.startsWith("APP-")) return `/erp/approvals/${id}`;
  return null;
}
