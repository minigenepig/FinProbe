import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createInvestigation, getErp } from "../api/client";
import { RESOURCES, type ErpResource } from "../erpCatalog";
import { displayCell, docPath } from "../format";
import { LoadingBar } from "../components/LoadingBar";

function flatten(obj: Record<string, unknown>, prefix = ""): Array<[string, unknown]> {
  const rows: Array<[string, unknown]> = [];
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      rows.push(...flatten(v as Record<string, unknown>, key));
    } else {
      rows.push([key, v]);
    }
  }
  return rows;
}

function linkFor(key: string, value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  if (key === "id" || key.endsWith("supplierId") || value.startsWith("VEN-")) return `/erp/vendors/${value}`;
  const mapped = docPath(value);
  if (mapped) return mapped;
  if (key.endsWith("poId") || key === "purchaseOrderId") return `/erp/purchase-orders/${value}`;
  if (key.endsWith("grId")) return `/erp/goods-receipts/${value}`;
  if (key.endsWith("invoiceId")) return `/erp/invoices/${value}`;
  if (key.endsWith("paymentId")) return `/erp/payments/${value}`;
  if (key.endsWith("approvalId")) return `/erp/approvals/${value}`;
  return null;
}

export default function EntityDetailPage() {
  const { resource, id } = useParams();
  const navigate = useNavigate();
  const meta = RESOURCES[resource as ErpResource];
  const [row, setRow] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!meta || !id) return;
    setError(null);
    setLoading(true);
    setRow(null);
    getErp(meta.path, id)
      .then(setRow)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [meta, id]);

  if (!meta) return <div className="page banner err">未知数据对象</div>;

  async function investigate() {
    if (!row) return;
    setBusy(true);
    try {
      const snap = await createInvestigation(meta.question(row), meta.wantReport);
      navigate(`/investigate/${snap.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const fields = row ? flatten(row).filter(([, v]) => !Array.isArray(v)) : [];
  const arrays = row
    ? Object.entries(row).filter(([, v]) => Array.isArray(v) && (v as unknown[]).length)
    : [];

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 12 }}>
        <h2 className="page-title" style={{ margin: 0 }}>{meta.title} · {id}</h2>
        <div className="chat-actions">
          <Link className="btn ghost" to={`/erp/${meta.path}`}>返回列表</Link>
          <button className="btn" disabled={busy || !row} onClick={investigate}>
            {meta.path === "policies" ? "制度问答" : "调查风险"}
          </button>
        </div>
      </div>
      {error && <div className="banner err">{error}</div>}
      {loading && <LoadingBar label={`正在加载${meta.title}详情…`} />}
      {!loading && row && <div className="card card-body">
        <h3>字段明细</h3>
        <div className="kv">
          {fields.map(([k, v]) => {
            const text = displayCell(v);
            const href = typeof v === "string" ? linkFor(k, v) : null;
            const skipSelf = href && (k === meta.idField || k.endsWith(`.${meta.idField}`));
            return (
              <div className="kv-pair" key={k}>
                <div className="k">{k}</div>
                <div>{href && !skipSelf ? <Link to={href}>{text}</Link> : text}</div>
              </div>
            );
          })}
        </div>
      </div>}
      {arrays.map(([key, value]) => {
        const list = value as Array<Record<string, unknown> | unknown>;
        const objects = list.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>;
        const cols = objects[0] ? Object.keys(objects[0]) : [];
        return (
          <div className="card card-body" key={key} style={{ marginTop: 12 }}>
            <h3>{key}（{list.length}）</h3>
            {objects.length ? (
              <table className="data">
                <thead>
                  <tr>{cols.map((col) => <th key={col}>{col}</th>)}</tr>
                </thead>
                <tbody>
                  {objects.map((item, idx) => (
                    <tr key={idx}>
                      {cols.map((col) => {
                        const cell = item[col];
                        const href = typeof cell === "string" ? linkFor(col, cell) : null;
                        return (
                          <td key={col}>
                            {href ? <Link to={href}>{displayCell(cell)}</Link> : displayCell(cell)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <pre className="pre">{JSON.stringify(list, null, 2)}</pre>
            )}
          </div>
        );
      })}
      {row && (
        <div className="card card-body" style={{ marginTop: 12 }}>
          <h3>原始记录</h3>
          <pre className="pre">{JSON.stringify(row, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
