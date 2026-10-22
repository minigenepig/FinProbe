export const RISK_TYPES = [
  "供应商主信息异常",
  "供应商之间关联关系风险",
  "少货多付 / 数量/金额异常",
  "拆单避审",
  "重复发票",
  "税率异常",
  "重复付款",
  "异常收款账户",
] as const;

export const RISK_TYPE_SHORT: Record<string, string> = {
  "供应商主信息异常": "主信息",
  "供应商之间关联关系风险": "关联",
  "少货多付 / 数量/金额异常": "三单",
  "拆单避审": "拆单",
  "重复发票": "重票",
  "税率异常": "税率",
  "重复付款": "重付",
  "异常收款账户": "收款户",
};

export interface Subject {
  supplierId?: string | null;
  supplierName?: string | null;
  poId?: string | null;
  grId?: string | null;
  invoiceId?: string | null;
  paymentId?: string | null;
  taxNo?: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "clarify";
  content: string;
  ts: string;
}

export interface Finding {
  riskType: string;
  riskLevel: string;
  facts?: string[];
  metrics?: Record<string, unknown>;
  rootCause?: string;
  mitigation?: Record<string, unknown> | string;
  recommendation?: string;
  openQuestions?: string[];
  evidenceRefs?: Array<{ tool?: string; id?: string }>;
  subject?: Subject;
}

export interface Envelope {
  skill?: string;
  agent?: string;
  subject?: Subject;
  queries?: Array<{
    tool: string;
    args?: Record<string, unknown>;
    ok?: boolean;
    totalCount?: number | null;
    artifactId?: string | null;
    error?: string | null;
  }>;
  findings?: Finding[];
  overallRiskLevel?: string | null;
  answer?: string;
  handoff?: unknown;
}

export interface InvestigationSnapshot {
  id: string;
  status: string;
  eventSeq: number;
  question: string;
  wantReport: boolean;
  mode: string | null;
  scope: string | null;
  subject: Subject;
  agents: string[];
  skills: string[];
  reason: string | null;
  clarifyQuestion: string | null;
  answer: string | null;
  envelopes: Envelope[];
  evidenceReview: Record<string, unknown> | null;
  report: Record<string, unknown> | null;
  reportMarkdown?: string | null;
  followUpRound: number;
  overallRiskLevel: string | null;
  messages: ChatMessage[];
  error: { code: string; message: string; retryable: boolean } | null;
  createdAt: string;
  updatedAt: string;
}

export interface InvestigationEvent {
  seq: number;
  type: string;
  ts: string;
  payload: Record<string, unknown>;
}

export interface PageResult<T = Record<string, unknown>> {
  ok: true;
  resource: string;
  totalCount: number;
  page: number;
  pageSize: number;
  data: T[];
}

export interface GoldEvidence {
  tool?: string;
  id?: string;
}

export interface GoldFinding {
  riskType: string;
  riskLevel: string;
  domain?: string;
  agent?: string;
  skill?: string;
  rootCause?: string;
  recommendation?: string;
  facts?: string[];
  metrics?: Record<string, unknown>;
  evidence?: GoldEvidence[];
  documentIds?: string[];
  approvalStatus?: string;
  openQuestions?: string[];
}

export interface GoldVendor {
  caseId: string;
  supplierId: string;
  name: string;
  category: string;
  alias?: string | null;
  overallRiskLevel: string;
  findingCount: number;
  mustDetectCount?: number;
  findings: GoldFinding[];
  typeLevels: Record<string, string>;
  notes?: string | null;
  question?: string;
}

export interface SupplierRiskBoard {
  source: string | null;
  datasetId?: string | null;
  status?: string | null;
  goldFrozen?: boolean;
  vendorCount: number;
  riskTypes: string[];
  levelCounts: Record<string, number>;
  domainCounts: Record<string, number>;
  typeLevelCounts: Record<string, Record<string, number>>;
  vendors: GoldVendor[];
  disclaimer?: string;
}

export interface DashboardSummary {
  ok: true;
  erpOk?: boolean;
  erpError?: string | null;
  counts: Record<string, number>;
  kpis: Record<string, number>;
  vendorByCategory: Record<string, number>;
  poByStatus: Record<string, number>;
  paymentByStatus: Record<string, number>;
  approvalByStatus: Record<string, number>;
  invoiceByTaxRate: Record<string, number>;
  poAmountByMonth: Record<string, number>;
  invoiceAmountByMonth?: Record<string, number>;
  paymentAmountByMonth?: Record<string, number>;
  poAmountByCategory?: Record<string, number>;
  topSuppliersByPoAmount: Array<{ supplierId: string; name: string; amount: number }>;
  duplicatePhones?: Array<{ phone: string; supplierIds: string[]; count: number }>;
  personalPayees?: Array<{ paymentId: string; invoiceId?: string; payeeName: string; amount: number }>;
  recentInvestigations: Array<{
    id: string;
    status: string;
    question: string;
    overallRiskLevel: string | null;
    mode: string | null;
    updatedAt: string;
  }>;
  supplierRisks?: SupplierRiskBoard;
}
