import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createInvestigation, listErp } from "../api/client";
import { RESOURCES, cellValue, type ErpResource } from "../erpCatalog";
import { displayCell, docPath } from "../format";
import { LoadingBar } from "../components/LoadingBar";

export default function EntityListPage() {
  const { resource } = useParams();
  const navigate = useNavigate();
  const meta = RESOURCES[resource as ErpResource];
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState("");
  const [total, setTotal] = useState(0);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    setPage(1);
    setKeyword("");
    setRows([]);
  }, [resource]);

  useEffect(() => {
    if (!meta) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listErp(meta.path, { page, pageSize, keyword })
      .then((res) => {
        if (cancelled) return;
        const next = (res.data || []).filter((row) => String(row[meta.idField] || "").trim());
        setRows(next);
        setTotal(res.totalCount || next.length);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setRows([]);
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [meta, page, pageSize, keyword]);

  if (!meta) return <div className="page banner err">未知数据对象</div>;

  async function investigate(row: Record<string, unknown>) {
    const id = String(row[meta.idField] || "");
    setBusyId(id);
    try {
      const snap = await createInvestigation(meta.question(row), meta.wantReport);
      navigate(`/investigate/${snap.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="page">
      <h2 className="page-title">{meta.title}</h2>
      <div className="toolbar">
        <input
          className="search"
          placeholder="关键字搜索"
          defaultValue={keyword}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setKeyword((e.target as HTMLInputElement).value.trim());
              setPage(1);
            }
          }}
        />
        <select
          value={pageSize}
          onChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(1);
          }}
        >
          <option value={20}>20 条/页</option>
          <option value={50}>50 条/页</option>
          <option value={100}>100 条/页</option>
        </select>
        <span className="muted">共 {total} 条</span>
      </div>
      {error && <div className="banner err">{error}</div>}
      {loading ? (
        <LoadingBar label={`正在加载${meta.title}…`} />
      ) : (
        <>
          <div className="card">
            <table className="data">
              <thead>
                <tr>
                  {meta.columns.map((col) => <th key={col.key}>{col.title}</th>)}
                  <th style={{ width: 120 }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const id = String(row[meta.idField] || "");
                  return (
                    <tr key={id}>
                      {meta.columns.map((col) => {
                        const value = cellValue(row, col.key);
                        const text = displayCell(value);
                        const href = col.key === meta.idField
                          ? `/erp/${meta.path}/${encodeURIComponent(id)}`
                          : typeof value === "string" ? docPath(value) : null;
                        return (
                          <td key={col.key}>
                            {href ? <Link to={href}>{text}</Link> : text}
                          </td>
                        );
                      })}
                      <td>
                        <button className="btn small" disabled={busyId === id} onClick={() => investigate(row)}>
                          {meta.path === "policies" ? "制度问答" : "调查风险"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {!rows.length && (
                  <tr>
                    <td colSpan={meta.columns.length + 1} className="muted">没有符合条件的记录</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <button className="btn ghost small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</button>
            <span>{page} / {pages}</span>
            <button className="btn ghost small" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>下一页</button>
          </div>
        </>
      )}
    </div>
  );
}
