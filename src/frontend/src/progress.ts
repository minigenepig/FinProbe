export const AGENT_LABEL: Record<string, string> = {
  LeadAgent: "路由",
  SupplierRiskAgent: "供应商",
  TransactionRiskAgent: "交易三单",
  PaymentRiskAgent: "付款",
  GeneralQueryAgent: "综合查询",
  EvidenceReviewAgent: "证据审核",
  ReportAgent: "报告",
};

export type ProgressKind = "phase" | "thought" | "action" | "observe" | "result";

export interface ProgressStep {
  seq: number;
  kind: ProgressKind;
  agent?: string;
  title: string;
  detail?: string;
  ok?: boolean;
}

export interface ProgressGroup {
  agent: string;
  label: string;
  status?: string;
  level?: string;
  degraded?: boolean;
  steps: ProgressStep[];
}

const SKIP = new Set(["heartbeat", "envelope.upserted", "message.assistant", "message.clarify"]);

function asText(value: unknown): string {
  if (value == null) return "";
  return String(value);
}

function toolAction(payload: Record<string, unknown>): string {
  const label = asText(payload.label) || asText(payload.tool) || "查询";
  const target = asText(payload.target);
  return target ? `${label}（${target}）` : label;
}

function toolObserve(payload: Record<string, unknown>): string {
  const observation = asText(payload.observation);
  if (observation) return observation;
  if (payload.ok === false) return asText(payload.error) || "调用失败";
  const n = payload.totalCount;
  if (n === 0) return "未检索到记录";
  if (typeof n === "number") return `共 ${n} 条`;
  return "已返回结果";
}

export function buildProgress(events: Array<{ seq: number; type: string; payload?: Record<string, unknown> }>): {
  phases: ProgressStep[];
  groups: ProgressGroup[];
} {
  const phases: ProgressStep[] = [];
  const order: string[] = [];
  const map = new Map<string, ProgressGroup>();

  function group(agent: string): ProgressGroup {
    if (!map.has(agent)) {
      order.push(agent);
      map.set(agent, { agent, label: AGENT_LABEL[agent] || agent, steps: [] });
    }
    return map.get(agent)!;
  }

  for (const ev of events) {
    if (SKIP.has(ev.type)) continue;
    const p = ev.payload || {};
    const agent = asText(p.agent);
    if (ev.type === "status.changed") {
      continue;
    }
    if (ev.type === "route.decided") {
      phases.push({
        seq: ev.seq,
        kind: "phase",
        title: `已拆分：${asText(p.mode)} / ${asText(p.scope)}`,
        detail: asText(p.reason),
      });
      continue;
    }
    if (ev.type === "agent.started" && agent) {
      const g = group(agent);
      g.status = "进行中";
      continue;
    }
    if (ev.type === "agent.thought" && agent) {
      const thought = asText(p.thought);
      if (!thought) continue;
      group(agent).steps.push({ seq: ev.seq, kind: "thought", agent, title: thought });
      continue;
    }
    if (ev.type === "tool.started" && agent) {
      group(agent).steps.push({ seq: ev.seq, kind: "action", agent, title: toolAction(p) });
      continue;
    }
    if (ev.type === "tool.completed" && agent) {
      group(agent).steps.push({
        seq: ev.seq,
        kind: "observe",
        agent,
        title: toolObserve(p),
        ok: p.ok !== false,
      });
      continue;
    }
    if (ev.type === "agent.completed" && agent) {
      const g = group(agent);
      g.status = p.degraded ? "证据不足" : "完成";
      g.level = asText(p.overallRiskLevel) || undefined;
      g.degraded = Boolean(p.degraded);
      const level = asText(p.overallRiskLevel);
      g.steps.push({
        seq: ev.seq,
        kind: "result",
        agent,
        title: level ? `本域结论：${level}` : "本域调查结束",
        ok: !p.degraded,
      });
      continue;
    }
    if (ev.type === "evidence.completed") {
      const g = group("EvidenceReviewAgent");
      g.steps.push({
        seq: ev.seq,
        kind: "observe",
        agent: "EvidenceReviewAgent",
        title: p.readyForReport ? "证据已齐，可以出报告" : "证据有缺口，需要补查或出草稿",
        ok: Boolean(p.readyForReport),
      });
      continue;
    }
    if (ev.type === "report.completed") {
      const g = group("ReportAgent");
      g.status = "完成";
      g.level = asText(p.overallRiskLevel) || undefined;
      g.steps.push({
        seq: ev.seq,
        kind: "result",
        agent: "ReportAgent",
        title: p.draft ? "已生成草稿报告" : `报告已生成${p.overallRiskLevel ? " · " + p.overallRiskLevel : ""}`,
        ok: !p.draft,
      });
      continue;
    }
    if (ev.type === "error") {
      const who = agent || "LeadAgent";
      group(who).steps.push({
        seq: ev.seq,
        kind: "observe",
        agent: who,
        title: p.isolated ? "该域降级为证据不足，其他域继续" : asText(p.message) || "出现错误",
        ok: false,
      });
    }
  }

  return { phases, groups: order.map((key) => map.get(key)!).filter(Boolean) };
}

export function latestLiveLines(groups: ProgressGroup[], limit = 6): string[] {
  const lines: string[] = [];
  for (const group of groups) {
    const last = group.steps[group.steps.length - 1];
    if (!last) continue;
    const tag = last.kind === "thought" ? "思考" : last.kind === "action" ? "行动" : last.kind === "observe" ? "观察" : "结论";
    lines.push(`${group.label} · ${tag} ${last.title}`);
  }
  return lines.slice(-limit);
}
