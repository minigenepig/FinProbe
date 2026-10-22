import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getInvestigation, getReport } from "../api/client";
import { levelClass, stripCompany } from "../format";
import { LoadingBar } from "../components/LoadingBar";

export default function ReportPage() {
  const { id } = useParams();
  const [markdown, setMarkdown] = useState<string>("");
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [draft, setDraft] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    getInvestigation(id)
      .then((snap) => {
        const flag = Boolean((snap.evidenceReview || {}).readyForReport);
        setReady(flag);
      })
      .catch(() => undefined);
    getReport(id)
      .then((res) => {
        setReport(res.report);
        setMarkdown(stripCompany(res.markdown || ""));
        setDraft(res.draft);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 12 }}>
        <h2 className="page-title" style={{ margin: 0 }}>风险报告</h2>
        <div className="chat-actions">
          <Link className="btn ghost" to={`/investigate/${id}`}>返回对话</Link>
          <Link className="btn ghost" to={`/investigate/${id}/evidence`}>证据详情</Link>
        </div>
      </div>
      {ready === false && <div className="banner">证据尚未 readyForReport，以下若有内容仅为草稿，不作为终稿。</div>}
      {draft && <div className="banner">当前为草稿报告。</div>}
      {error && <div className="banner err">{error}</div>}
      {report && (
        <div className="kpis">
          <div className="card kpi">
            <div className={`n ${levelClass(String(report.overallRiskLevel || ""))}`}>{String(report.overallRiskLevel || "—")}</div>
            <div className="l">总体风险</div>
          </div>
          <div className="card kpi"><div className="n">{String(report.reportId || "—")}</div><div className="l">报告编号</div></div>
        </div>
      )}
      {loading ? <LoadingBar label="正在加载风险报告…" /> : markdown ? <pre className="pre report-md">{markdown}</pre> : !error ? <div className="muted">暂无报告</div> : null}
    </div>
  );
}
