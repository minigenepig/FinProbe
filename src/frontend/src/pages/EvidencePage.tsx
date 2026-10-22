import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getInvestigation } from "../api/client";
import { displayCell, docPath, levelClass, stripCompany } from "../format";
import { LoadingBar } from "../components/LoadingBar";
import type { Envelope, InvestigationSnapshot } from "../types";

function QueryTable({ env }: { env: Envelope }) {
  const rows = env.queries || [];
  if (!rows.length) return <div className="muted">无查询记录</div>;
  return (
    <table className="data">
      <thead>
        <tr>
          <th>工具</th>
          <th>成功</th>
          <th>条数</th>
          <th>artifact</th>
          <th>参数</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((q, idx) => (
          <tr key={`${q.tool}-${idx}`}>
            <td>{q.tool}</td>
            <td>{q.ok === false ? "否" : "是"}</td>
            <td>{q.totalCount ?? "—"}</td>
            <td>{q.artifactId || "—"}</td>
            <td className="clip">{JSON.stringify(q.args || {})}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function EvidencePage() {
  const { id } = useParams();
  const [snap, setSnap] = useState<InvestigationSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getInvestigation(id).then(setSnap).catch((err: Error) => setError(err.message));
  }, [id]);

  if (error) return <div className="page"><div className="banner err">{error}</div></div>;
  if (!snap) return <div className="page"><LoadingBar label="正在加载证据详情…" /></div>;

  const review = snap.evidenceReview || {};
  const followUps = (review.followUpTasks as Array<Record<string, unknown>> | undefined) || [];

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 12 }}>
        <div>
          <h2 className="page-title" style={{ margin: 0 }}>证据详情</h2>
          <div className="muted">{snap.id} · {snap.mode || "—"} / {snap.scope || "—"}</div>
        </div>
        <div className="chat-actions">
          <Link className="btn ghost" to={`/investigate/${snap.id}`}>返回对话</Link>
          <Link className="btn ghost" to={`/investigate/${snap.id}/report`}>风险报告</Link>
        </div>
      </div>

      <div className="kpis">
        <div className="card kpi"><div className={`n ${levelClass(snap.overallRiskLevel)}`}>{snap.overallRiskLevel || "—"}</div><div className="l">总体风险</div></div>
        <div className="card kpi"><div className="n">{snap.envelopes?.length || 0}</div><div className="l">调查信封</div></div>
        <div className="card kpi"><div className="n">{String(review.readyForReport ?? "—")}</div><div className="l">readyForReport</div></div>
        <div className="card kpi"><div className="n">{snap.followUpRound}</div><div className="l">补查轮次</div></div>
      </div>

      {(snap.envelopes || []).map((env, idx) => (
        <div className="card card-body" key={`${env.skill}-${idx}`} style={{ marginBottom: 12 }}>
          <div className="row">
            <h3>{env.skill || env.agent || "信封"}</h3>
            <span className={levelClass(env.overallRiskLevel)}>{env.overallRiskLevel || "—"}</span>
          </div>
          <div className="muted" style={{ marginBottom: 8 }}>{env.agent} · {JSON.stringify(env.subject || {})}</div>
          <h4>查询</h4>
          <QueryTable env={env} />
          {(env.findings || []).map((finding, fidx) => (
            <div className="finding" key={`${finding.riskType}-${fidx}`}>
              <div className="row">
                <strong>{finding.riskType}</strong>
                <span className={levelClass(finding.riskLevel)}>{finding.riskLevel}</span>
              </div>
              {finding.rootCause && <p>{stripCompany(finding.rootCause)}</p>}
              {!!finding.facts?.length && (
                <ul>{finding.facts.map((fact) => <li key={fact}>{stripCompany(fact)}</li>)}</ul>
              )}
              {finding.metrics && <pre className="pre">{JSON.stringify(finding.metrics, null, 2)}</pre>}
              <div className="chips">
                {(finding.evidenceRefs || []).map((ref, ridx) => {
                  const href = ref.id ? docPath(String(ref.id)) : null;
                  return href ? (
                    <Link className="chip" key={`${ref.id}-${ridx}`} to={href}>{ref.tool} {ref.id}</Link>
                  ) : (
                    <span className="chip" key={`${ref.tool}-${ridx}`}>{ref.tool} {ref.id}</span>
                  );
                })}
              </div>
              {finding.mitigation && (
                <div className="muted">消解：{displayCell(finding.mitigation)}</div>
              )}
            </div>
          ))}
        </div>
      ))}

      <div className="card card-body">
        <h3>证据审核</h3>
        <pre className="pre">{JSON.stringify(review, null, 2)}</pre>
        {!!followUps.length && (
          <div>
            <h4>补查任务</h4>
            <ul>
              {followUps.map((task, idx) => (
                <li key={idx}>{String(task.agent)} / {String(task.skill)} / {String(task.tool)} — {String(task.reason || "")}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
