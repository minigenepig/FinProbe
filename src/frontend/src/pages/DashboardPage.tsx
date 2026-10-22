import { Fragment, useEffect, useMemo, useState } from "react";
import { LoadingBar } from "../components/LoadingBar";
import { Link, useNavigate } from "react-router-dom";
import { createInvestigation, getDashboard } from "../api/client";
import { RISK_TYPE_SHORT } from "../types";
import { STATUS_LABEL, docPath, heatClass, levelClass, money, stripCompany } from "../format";
import type { DashboardSummary, GoldVendor } from "../types";

const LEVELS = ["高风险", "中风险", "低风险", "证据不足"];
const DONUT_COLORS: Record<string, string> = {
  "高风险": "#f5222d",
  "中风险": "#d48806",
  "低风险": "#389e0d",
  "证据不足": "#8c8c8c",
};

function Bars({ data, moneyMode }: { data: Record<string, number>; moneyMode?: boolean }) {
  const entries = Object.entries(data || {});
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <div className="bars">
      {entries.map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span title={k}>{k}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(v / max) * 100}%` }} /></div>
          <span className="bar-val">{moneyMode || v > 1000 ? money(v) : v}</span>
        </div>
      ))}
      {!entries.length && <div className="muted">暂无数据</div>}
    </div>
  );
}

function Donut({ counts }: { counts: Record<string, number> }) {
  const total = Math.max(LEVELS.reduce((s, k) => s + (counts[k] || 0), 0), 1);
  let cursor = 0;
  const stops: string[] = [];
  for (const level of LEVELS) {
    const pct = ((counts[level] || 0) / total) * 100;
    const next = cursor + pct;
    stops.push(`${DONUT_COLORS[level]} ${cursor}% ${next}%`);
    cursor = next;
  }
  return (
    <div className="donut-wrap">
      <div className="donut" style={{ background: `conic-gradient(${stops.join(",")})` }} />
      <div className="donut-legend">
        {LEVELS.map((level) => (
          <div key={level}><i className="swatch" style={{ background: DONUT_COLORS[level] }} />{level} {counts[level] || 0}</div>
        ))}
      </div>
    </div>
  );
}

function StackedTypes({ data }: { data: Record<string, Record<string, number>> }) {
  const rows = Object.entries(data || {});
  const max = Math.max(
    ...rows.map(([, counts]) => LEVELS.reduce((s, k) => s + (counts[k] || 0), 0)),
    1,
  );
  return (
    <div className="bars">
      {rows.map(([type, counts]) => {
        const total = LEVELS.reduce((s, k) => s + (counts[k] || 0), 0);
        return (
          <div className="stack-row" key={type}>
            <span title={type}>{RISK_TYPE_SHORT[type] || type}</span>
            <div className="stack-track">
              {LEVELS.map((level) => {
                const v = counts[level] || 0;
                if (!v) return null;
                return (
                  <div
                    key={level}
                    className={`stack-seg ${heatClass(level)}`}
                    style={{ width: `${(v / max) * 100}%` }}
                    title={`${level} ${v}`}
                  />
                );
              })}
            </div>
            <span className="bar-val">{total}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState("全部");
  const [category, setCategory] = useState("全部");
  const [keyword, setKeyword] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    getDashboard().then(setData).catch((err: Error) => setError(err.message));
  }, []);

  const board = data?.supplierRisks;
  const vendors = board?.vendors || [];
  const categories = useMemo(
    () => Array.from(new Set(vendors.map((v) => v.category).filter(Boolean))).sort(),
    [vendors],
  );

  const filtered = useMemo(() => {
    return vendors.filter((row) => {
      if (level !== "全部" && row.overallRiskLevel !== level) return false;
      if (category !== "全部" && row.category !== category) return false;
      if (keyword) {
        const blob = `${row.supplierId} ${row.name} ${row.notes || ""}`.toLowerCase();
        if (!blob.includes(keyword.toLowerCase())) return false;
      }
      return true;
    });
  }, [vendors, level, category, keyword]);

  async function investigateVendor(row: GoldVendor) {
    setBusyId(row.supplierId);
    try {
      const question = row.question || `请全面排查供应商 ${row.supplierId} ${row.name || ""}`;
      const snap = await createInvestigation(question, true);
      navigate(`/investigate/${snap.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (error && !data) return <div className="page"><div className="banner err">{error}</div></div>;
  if (!data) return <div className="page"><LoadingBar label="正在加载数据看板…" /></div>;
  const k = data.kpis || {};
  const counts = board?.levelCounts || {};

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 8 }}>
        <div>
          <h2 className="page-title" style={{ margin: 0 }}>数据看板</h2>
          <div className="muted">主数据规模、资金分布与 27 家供应商全量调查结果</div>
        </div>
      </div>
      {data.erpOk === false && <div className="banner">ERP 暂不可用：{data.erpError || "无法连接"}。供应商调查结果仍可查看。</div>}
      {error && <div className="banner err">{error}</div>}

      <div className="kpis">
        <div className="card kpi"><div className="n">{k.vendorCount}</div><div className="l">供应商</div></div>
        <div className="card kpi"><div className="n">{k.activeVendorCount ?? "—"}</div><div className="l">启用供应商</div></div>
        <div className="card kpi"><div className="n">{k.poCount}</div><div className="l">采购订单</div></div>
        <div className="card kpi"><div className="n">{data.counts.goodsReceipts ?? k.grCount ?? "—"}</div><div className="l">入库单</div></div>
        <div className="card kpi"><div className="n">{k.invoiceCount}</div><div className="l">发票</div></div>
        <div className="card kpi"><div className="n">{k.paymentCount}</div><div className="l">付款单</div></div>
        <div className="card kpi"><div className="n">{k.approvalCount}</div><div className="l">审批</div></div>
        <div className="card kpi"><div className="n">{k.pendingApprovalCount ?? "—"}</div><div className="l">待审审批</div></div>
        <div className="card kpi"><div className="n">{money(k.poAmountSum)}</div><div className="l">PO 价税合计</div></div>
        <div className="card kpi"><div className="n">{money(k.invoiceAmountSum)}</div><div className="l">发票合计</div></div>
        <div className="card kpi"><div className="n">{money(k.paymentAmountSum)}</div><div className="l">付款合计</div></div>
        <div className="card kpi"><div className="n">{money(k.amountGapInvoiceMinusPo)}</div><div className="l">发票-PO 差额</div></div>
      </div>

      <h3 className="section-title">27 家供应商全量调查</h3>
      {board?.disclaimer && <div className="muted" style={{ marginBottom: 8 }}>{stripCompany(board.disclaimer)}</div>}
      <div className="kpis">
        <div className="card kpi accent-high"><div className="n">{counts["高风险"] || 0}</div><div className="l">高风险供应商</div></div>
        <div className="card kpi accent-mid"><div className="n">{counts["中风险"] || 0}</div><div className="l">中风险供应商</div></div>
        <div className="card kpi accent-low"><div className="n">{counts["低风险"] || 0}</div><div className="l">低风险供应商</div></div>
        <div className="card kpi accent-gap"><div className="n">{counts["证据不足"] || 0}</div><div className="l">证据不足</div></div>
        <div className="card kpi"><div className="n">{board?.vendorCount || 0}</div><div className="l">覆盖供应商</div></div>
        <div className="card kpi"><div className="n">{vendors.reduce((s, v) => s + v.findingCount, 0)}</div><div className="l">必检发现条数</div></div>
      </div>

      <div className="grid-3" style={{ marginBottom: 12 }}>
        <div className="card card-body"><h3>总体风险分布</h3><Donut counts={counts} /></div>
        <div className="card card-body"><h3>风险类型（必检发现）</h3><StackedTypes data={board?.typeLevelCounts || {}} /></div>
        <div className="card card-body"><h3>风险领域</h3><Bars data={board?.domainCounts || {}} /></div>
      </div>

      <div className="card card-body" style={{ marginBottom: 12 }}>
        <h3>风险热力图（8 类 × 27 家）</h3>
        <div className="matrix-wrap">
          <table className="data matrix">
            <thead>
              <tr>
                <th>供应商</th>
                {(board?.riskTypes || Object.keys(RISK_TYPE_SHORT)).map((type) => (
                  <th key={type} title={type}>{RISK_TYPE_SHORT[type] || type}</th>
                ))}
                <th>总体</th>
              </tr>
            </thead>
            <tbody>
              {vendors.map((row) => (
                <tr key={row.supplierId} className={openId === row.supplierId ? "selected" : undefined} onClick={() => setOpenId(row.supplierId)}>
                  <td>
                    <div>{row.supplierId}</div>
                    <div className="muted clip">{row.name}</div>
                  </td>
                  {(board?.riskTypes || []).map((type) => (
                    <td key={type} className={heatClass(row.typeLevels?.[type])} title={`${type} ${row.typeLevels?.[type] || "低风险"}`}>
                      {(row.typeLevels?.[type] || "低风险").slice(0, 1)}
                    </td>
                  ))}
                  <td className={levelClass(row.overallRiskLevel)}>{row.overallRiskLevel}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card card-body" style={{ marginBottom: 16 }}>
        <div className="row" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>供应商调查明细</h3>
          <div className="toolbar" style={{ margin: 0 }}>
            <select value={level} onChange={(e) => setLevel(e.target.value)}>
              <option>全部</option>
              {LEVELS.map((item) => <option key={item}>{item}</option>)}
            </select>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option>全部</option>
              {categories.map((item) => <option key={item}>{item}</option>)}
            </select>
            <input className="search" placeholder="搜索供应商" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
            <span className="muted">{filtered.length} / {vendors.length}</span>
          </div>
        </div>
        <table className="data">
          <thead>
            <tr>
              <th>供应商</th>
              <th>名称</th>
              <th>类别</th>
              <th>总体</th>
              <th>发现</th>
              <th>风险类型</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <Fragment key={row.supplierId}>
                <tr key={row.supplierId}>
                  <td><Link to={`/erp/vendors/${row.supplierId}`}>{row.supplierId}</Link></td>
                  <td>{row.name}</td>
                  <td>{row.category}</td>
                  <td className={levelClass(row.overallRiskLevel)}>{row.overallRiskLevel}</td>
                  <td>{row.findingCount}</td>
                  <td>
                    <div className="chips">
                      {row.findings.map((item, idx) => (
                        <span className={`chip ${levelClass(item.riskLevel)}`} key={`${item.riskType}-${idx}`}>
                          {RISK_TYPE_SHORT[item.riskType] || item.riskType} {item.riskLevel}
                        </span>
                      ))}
                      {!row.findings.length && <span className="chip">背景低风险</span>}
                    </div>
                  </td>
                  <td>
                    <div className="chat-actions">
                      <button className="btn ghost small" onClick={() => setOpenId(openId === row.supplierId ? null : row.supplierId)}>
                        {openId === row.supplierId ? "收起" : "详情"}
                      </button>
                      <button className="btn small" disabled={busyId === row.supplierId} onClick={() => investigateVendor(row)}>
                        调查风险
                      </button>
                    </div>
                  </td>
                </tr>
                {openId === row.supplierId && (
                  <tr key={`${row.supplierId}-open`}>
                    <td colSpan={7}>
                      <div className="expand">
                        {row.notes && <p className="muted">{stripCompany(row.notes)}</p>}
                        {(row.findings || []).map((item, idx) => (
                          <div className="finding" key={`${item.riskType}-${idx}`}>
                            <div className="row">
                              <strong>{item.domain} · {item.riskType}</strong>
                              <span className={levelClass(item.riskLevel)}>{item.riskLevel}</span>
                            </div>
                            {item.rootCause && <p>{stripCompany(item.rootCause)}</p>}
                            {!!item.facts?.length && <ul>{item.facts.map((fact) => <li key={fact}>{stripCompany(fact)}</li>)}</ul>}
                            <div className="chips">
                              {(item.documentIds || []).map((doc) => {
                                const href = docPath(doc);
                                return href ? <Link className="chip" key={doc} to={href}>{doc}</Link> : <span className="chip" key={doc}>{doc}</span>;
                              })}
                              {(item.evidence || []).map((ev, eidx) => (
                                <span className="chip" key={`${ev.tool}-${eidx}`}>{ev.tool} {ev.id}</span>
                              ))}
                            </div>
                            {item.recommendation && <div className="muted">建议：{stripCompany(item.recommendation)}</div>}
                          </div>
                        ))}
                        {!row.findings.length && <div className="muted">八类风险均未形成必检异常，总体低风险。</div>}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="section-title">主数据与资金分布</h3>
      <div className="grid-2">
        <div className="card card-body"><h3>供应商类别</h3><Bars data={data.vendorByCategory} /></div>
        <div className="card card-body"><h3>PO 金额（按类别）</h3><Bars data={data.poAmountByCategory || {}} moneyMode /></div>
        <div className="card card-body"><h3>PO 状态</h3><Bars data={data.poByStatus} /></div>
        <div className="card card-body"><h3>付款状态</h3><Bars data={data.paymentByStatus} /></div>
        <div className="card card-body"><h3>发票税率分布</h3><Bars data={data.invoiceByTaxRate} /></div>
        <div className="card card-body"><h3>审批状态</h3><Bars data={data.approvalByStatus} /></div>
        <div className="card card-body"><h3>PO 金额（按月）</h3><Bars data={data.poAmountByMonth} moneyMode /></div>
        <div className="card card-body"><h3>发票金额（按月）</h3><Bars data={data.invoiceAmountByMonth || {}} moneyMode /></div>
        <div className="card card-body"><h3>付款金额（按月）</h3><Bars data={data.paymentAmountByMonth || {}} moneyMode /></div>
        <div className="card card-body">
          <h3>户名像个人的付款（线索）</h3>
          <div className="muted" style={{ marginBottom: 8 }}>共 {k.personalPayeeHint || 0} 笔，不是风险结论。</div>
          <table className="data">
            <thead><tr><th>付款</th><th>发票</th><th>户名</th><th>金额</th></tr></thead>
            <tbody>
              {(data.personalPayees || []).map((row) => (
                <tr key={row.paymentId}>
                  <td><Link to={`/erp/payments/${row.paymentId}`}>{row.paymentId}</Link></td>
                  <td>{row.invoiceId ? <Link to={`/erp/invoices/${row.invoiceId}`}>{row.invoiceId}</Link> : "—"}</td>
                  <td>{row.payeeName}</td>
                  <td className="num">{money(row.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 12 }}>
        <div className="card card-body">
          <h3>PO 金额 Top 供应商</h3>
          <table className="data">
            <thead><tr><th>供应商</th><th>名称</th><th>金额</th><th></th></tr></thead>
            <tbody>
              {data.topSuppliersByPoAmount.map((row) => (
                <tr key={row.supplierId}>
                  <td><Link to={`/erp/vendors/${row.supplierId}`}>{row.supplierId}</Link></td>
                  <td>{row.name}</td>
                  <td className="num">{money(row.amount)}</td>
                  <td><Link className="btn small" to="/" state={{ question: `请全面排查供应商 ${row.supplierId}` }}>调查风险</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card card-body">
          <h3>共享电话线索</h3>
          <div className="muted" style={{ marginBottom: 8 }}>{k.duplicatePhoneGroups || 0} 组重复电话</div>
          <table className="data">
            <thead><tr><th>电话</th><th>供应商</th></tr></thead>
            <tbody>
              {(data.duplicatePhones || []).map((row) => (
                <tr key={row.phone}>
                  <td>{row.phone}</td>
                  <td className="chips">{row.supplierIds.map((sid) => <Link className="chip" key={sid} to={`/erp/vendors/${sid}`}>{sid}</Link>)}</td>
                </tr>
              ))}
              {!(data.duplicatePhones || []).length && <tr><td colSpan={2} className="muted">无共享电话</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card card-body" style={{ marginTop: 12 }}>
        <h3>最近调查</h3>
        <table className="data">
          <thead><tr><th>编号</th><th>状态</th><th>风险</th><th>问题</th></tr></thead>
          <tbody>
            {(data.recentInvestigations || []).map((row) => (
              <tr key={row.id}>
                <td><Link to={`/investigate/${row.id}`}>{row.id}</Link></td>
                <td>{STATUS_LABEL[row.status] || row.status}</td>
                <td className={levelClass(row.overallRiskLevel)}>{row.overallRiskLevel || "—"}</td>
                <td>{stripCompany(row.question)}</td>
              </tr>
            ))}
            {!(data.recentInvestigations || []).length && <tr><td colSpan={4} className="muted">暂无调查记录</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
