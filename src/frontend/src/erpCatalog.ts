export type ErpResource =
  | "vendors"
  | "purchase-orders"
  | "goods-receipts"
  | "invoices"
  | "payments"
  | "approvals"
  | "policies";

export interface Column {
  key: string;
  title: string;
}

export interface ResourceMeta {
  path: ErpResource;
  title: string;
  idField: string;
  columns: Column[];
  wantReport: boolean;
  question: (row: Record<string, unknown>) => string;
}

export const NAV_PRIMARY = [
  { to: "/", label: "调查工作台" },
  { to: "/dashboard", label: "数据看板" },
];

export const ERP_NAV = {
  label: "业务数据",
  children: [
    { to: "/erp/vendors", label: "供应商" },
    { to: "/erp/purchase-orders", label: "采购订单" },
    { to: "/erp/goods-receipts", label: "入库单" },
    { to: "/erp/invoices", label: "发票" },
    { to: "/erp/payments", label: "付款单" },
    { to: "/erp/approvals", label: "审批" },
    { to: "/erp/policies", label: "制度" },
  ],
};

export const NAV = [...NAV_PRIMARY, ...ERP_NAV.children];

function sid(row: Record<string, unknown>): string {
  const supplier = row.supplier as Record<string, unknown> | undefined;
  return String(supplier?.supplierId || row.supplierId || "");
}

function sname(row: Record<string, unknown>): string {
  const supplier = row.supplier as Record<string, unknown> | undefined;
  return String(supplier?.supplier_name || supplier?.name || "");
}

export const RESOURCES: Record<ErpResource, ResourceMeta> = {
  vendors: {
    path: "vendors",
    title: "供应商",
    idField: "id",
    columns: [
      { key: "id", title: "供应商编号" },
      { key: "name", title: "名称" },
      { key: "category", title: "类别" },
      { key: "taxNo", title: "税号" },
      { key: "contactPhone", title: "电话" },
      { key: "bankAccount", title: "银行账号" },
      { key: "active", title: "启用" },
    ],
    wantReport: true,
    question: (row) => `请全面排查供应商 ${row.id}${row.name ? " " + row.name : ""}`,
  },
  "purchase-orders": {
    path: "purchase-orders",
    title: "采购订单",
    idField: "poId",
    columns: [
      { key: "poId", title: "PO" },
      { key: "supplierId", title: "供应商" },
      { key: "orderDate", title: "订单日" },
      { key: "status", title: "状态" },
      { key: "totalWithTax", title: "价税合计" },
      { key: "taxRate", title: "税率" },
    ],
    wantReport: true,
    question: (row) => `${row.poId} 从采购到付款全面排查，能否付款？`,
  },
  "goods-receipts": {
    path: "goods-receipts",
    title: "入库单",
    idField: "grId",
    columns: [
      { key: "grId", title: "GR" },
      { key: "poId", title: "PO" },
      { key: "receivedDate", title: "入库日" },
      { key: "receivedBy", title: "收货人" },
      { key: "warehouse_location", title: "仓库" },
      { key: "status", title: "状态" },
    ],
    wantReport: true,
    question: (row) => `${row.grId} 对应入库是否存在三单数量/金额异常？PO=${row.poId || ""}`,
  },
  invoices: {
    path: "invoices",
    title: "发票",
    idField: "invoiceId",
    columns: [
      { key: "invoiceId", title: "发票" },
      { key: "purchaseOrderId", title: "PO" },
      { key: "supplierId", title: "供应商" },
      { key: "invoice_date", title: "开票日" },
      { key: "taxRate", title: "税率" },
      { key: "total", title: "价税合计" },
    ],
    wantReport: true,
    question: (row) => `${row.invoiceId} 请排查重复发票、税率异常、重复付款及收款账户风险`,
  },
  payments: {
    path: "payments",
    title: "付款单",
    idField: "paymentId",
    columns: [
      { key: "paymentId", title: "付款单" },
      { key: "invoiceId", title: "发票" },
      { key: "poId", title: "PO" },
      { key: "paymentDate", title: "付款日" },
      { key: "status", title: "状态" },
      { key: "paymentAmount", title: "金额" },
    ],
    wantReport: true,
    question: (row) => `${row.paymentId} 请排查重复付款与异常收款账户`,
  },
  approvals: {
    path: "approvals",
    title: "审批",
    idField: "approvalId",
    columns: [
      { key: "approvalId", title: "审批单" },
      { key: "businessType", title: "业务类型" },
      { key: "businessId", title: "业务单号" },
      { key: "approvalStatus", title: "状态" },
    ],
    wantReport: true,
    question: (row) => `审批单 ${row.approvalId} 关联 ${row.businessType || ""} ${row.businessId || ""}，请定位单据并做风险调查`,
  },
  policies: {
    path: "policies",
    title: "制度",
    idField: "docId",
    columns: [
      { key: "docId", title: "文档" },
      { key: "title", title: "标题" },
      { key: "fileName", title: "文件" },
      { key: "charCount", title: "字数" },
    ],
    wantReport: false,
    question: (row) => `${row.title || row.docId} 的现行条款是什么？`,
  },
};

export function cellValue(row: Record<string, unknown>, key: string): unknown {
  if (key === "supplierId") return sid(row);
  if (key === "supplierName") return sname(row);
  if (key.includes(".")) {
    return key.split(".").reduce<unknown>((acc, part) => {
      if (acc && typeof acc === "object") return (acc as Record<string, unknown>)[part];
      return undefined;
    }, row);
  }
  return row[key];
}