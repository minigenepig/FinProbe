import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  cancelInvestigation,
  createInvestigation,
  getInvestigation,
  openEventStream,
  postMessage,
} from "../api/client";
import { LoadingBar } from "../components/LoadingBar";
import { STATUS_LABEL, riskWordClass, stripCompany } from "../format";
import { buildProgress, latestLiveLines } from "../progress";
import type { InvestigationEvent, InvestigationSnapshot } from "../types";

const DEFAULT_QUESTION = "PO-01332 三单是否匹配？请给出能否付款的结论。";

function RiskResult({ snap }: { snap: InvestigationSnapshot }) {
  const findings = (snap.envelopes || []).flatMap((env) => env.findings || []);
  const answers = (snap.envelopes || [])
    .filter((env) => env.answer && !(env.findings || []).length)
    .map((env) => stripCompany(env.answer || ""));
  return (
    <div className="bubble assistant">
      <div className="meta">风险结果</div>
      {snap.overallRiskLevel && (
        <p>
          总体风险：<span className={riskWordClass(snap.overallRiskLevel)}>{snap.overallRiskLevel}</span>
        </p>
      )}
      {findings.map((finding, idx) => (
        <div className="risk-item" key={`${finding.riskType}-${idx}`}>
          <p>
            <strong>{finding.riskType}</strong>
            {"："}
            <span className={riskWordClass(finding.riskLevel)}>{finding.riskLevel}</span>
          </p>
          {finding.rootCause && (
            <p><strong>根因：</strong>{stripCompany(finding.rootCause)}</p>
          )}
          {finding.recommendation && (
            <p><strong>建议：</strong>{stripCompany(finding.recommendation)}</p>
          )}
        </div>
      ))}
      {answers.map((text, idx) => <p key={`ans-${idx}`}>{text}</p>)}
      {!findings.length && !answers.length && snap.answer && <p>{stripCompany(snap.answer)}</p>}
      <div className="chat-actions">
        <Link className="btn small ghost" to={`/investigate/${snap.id}/evidence`}>查看证据详情</Link>
        <Link className="btn small ghost" to={`/investigate/${snap.id}/report`}>查看风险报告</Link>
      </div>
    </div>
  );
}

export default function InvestigatePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const preset = (location.state as { question?: string } | null)?.question;
  const [question, setQuestion] = useState(preset || DEFAULT_QUESTION);
  const [snapshot, setSnapshot] = useState<InvestigationSnapshot | null>(null);
  const [events, setEvents] = useState<InvestigationEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(Boolean(id));
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const seqRef = useRef(0);
  const chatRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (id) return;
    if (preset) setQuestion(preset);
  }, [id, preset]);

  useEffect(() => {
    if (!id) {
      setSnapshot(null);
      setEvents([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setError(null);
    setEvents([]);
    setLoading(true);
    getInvestigation(id)
      .then((snap) => {
        if (cancelled) return;
        setSnapshot(snap);
        setLoading(false);
        connect(snap.id, 0);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });
    return () => {
      cancelled = true;
      esRef.current?.close();
    };
  }, [id]);

  useEffect(() => {
    const el = chatRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [snapshot, events, loading]);

  function connect(invId: string, afterSeq: number) {
    esRef.current?.close();
    seqRef.current = afterSeq;
    const es = openEventStream(
      invId,
      afterSeq,
      (ev) => {
        if (ev.type === "heartbeat") return;
        if (ev.seq && ev.seq <= seqRef.current) return;
        seqRef.current = Math.max(seqRef.current, ev.seq || 0);
        setEvents((prev) => [...prev, ev]);
        if (
          ev.type === "message.assistant" ||
          ev.type === "message.clarify" ||
          ev.type === "status.changed" ||
          ev.type === "envelope.upserted" ||
          ev.type === "report.completed" ||
          ev.type === "agent.completed" ||
          ev.type === "error"
        ) {
          getInvestigation(invId).then(setSnapshot).catch(() => undefined);
        }
      },
      () => {
        getInvestigation(invId)
          .then((snap) => {
            setSnapshot(snap);
            if (["completed", "failed", "cancelled"].includes(snap.status)) {
              esRef.current?.close();
              return;
            }
            window.setTimeout(() => connect(invId, seqRef.current), 800);
          })
          .catch(() => undefined);
      },
    );
    esRef.current = es;
  }

  async function start() {
    setBusy(true);
    setError(null);
    setEvents([]);
    try {
      const snap = await createInvestigation(question.trim());
      setQuestion("");
      navigate(`/investigate/${snap.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function reply() {
    if (!snapshot) return;
    setBusy(true);
    try {
      const snap = await postMessage(snapshot.id, question.trim());
      setSnapshot(snap);
      setQuestion("");
      connect(snap.id, snap.eventSeq);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const awaiting = snapshot?.status === "awaiting_user";
  const running = Boolean(snapshot && !["completed", "failed", "cancelled"].includes(snapshot.status));
  const progress = buildProgress(events);
  const liveLines = latestLiveLines(progress.groups);
  const hasUserMessage = (snapshot?.messages || []).some((msg) => msg.role === "user");

  return (
    <div className="workbench">
      <section className="chat-col">
        <div className="chat" ref={chatRef}>
          {loading && <LoadingBar label="正在打开调查…" />}
          {!loading && !snapshot && (
            <div className="muted">输入问题开始调查，或从业务数据列表点击「调查风险」。</div>
          )}
          {snapshot && !hasUserMessage && snapshot.question && (
            <div className="bubble user">
              <div className="meta">你</div>
              {stripCompany(snapshot.question)}
            </div>
          )}
          {(snapshot?.messages || []).map((msg, idx) => (
            <div key={`${msg.ts}-${idx}`} className={`bubble ${msg.role}`}>
              <div className="meta">{msg.role === "user" ? "你" : msg.role === "clarify" ? "需要澄清" : "调查助手"} · {msg.ts}</div>
              {stripCompany(msg.content)}
            </div>
          ))}
          {running && (
            <div className="bubble assistant live">
              <div className="meta">调查进行中 · {STATUS_LABEL[snapshot?.status || ""] || snapshot?.status}</div>
              <div className="loading-track"><div className="loading-bar" /></div>
              <ul className="live-log">
                {liveLines.map((line, idx) => (
                  <li key={`${line}-${idx}`}>{line}</li>
                ))}
                {!liveLines.length && <li>正在路由并调度领域 Agent…</li>}
              </ul>
            </div>
          )}
          {snapshot?.status === "completed" && <RiskResult snap={snapshot} />}
          {snapshot?.status === "failed" && snapshot.error && (
            <div className="bubble assistant">
              <div className="meta">调查失败</div>
              {snapshot.error.message}
            </div>
          )}
        </div>
        {error && <div className="banner err" style={{ margin: "0 16px 8px" }}>{error}</div>}
        <div className="composer">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={awaiting ? "回答澄清问题…" : "输入调查问题"}
          />
          <div className="row">
            <div className="chips">
              {snapshot?.id && <span className="chip">{snapshot.id}</span>}
              {snapshot?.status && <span className="chip">{STATUS_LABEL[snapshot.status] || snapshot.status}</span>}
              {snapshot?.mode && <span className="chip">{snapshot.mode}</span>}
              {snapshot?.overallRiskLevel && (
                <span className={`chip ${riskWordClass(snapshot.overallRiskLevel)}`}>{snapshot.overallRiskLevel}</span>
              )}
            </div>
            <div className="chat-actions">
              {running && (
                <button className="btn ghost danger" onClick={() => snapshot && cancelInvestigation(snapshot.id).then(setSnapshot)}>
                  取消
                </button>
              )}
              <button className="btn" disabled={busy || !question.trim()} onClick={awaiting ? reply : start}>
                {awaiting ? "提交澄清" : "开始调查"}
              </button>
            </div>
          </div>
        </div>
      </section>
      <aside className="progress-col">
        <div className="card-body" style={{ borderBottom: "1px solid var(--line)" }}>
          <strong>调查进度</strong>
          <div className="muted">{snapshot ? STATUS_LABEL[snapshot.status] || snapshot.status : "等待开始"}</div>
          {progress.phases[0] && <div className="muted" style={{ marginTop: 6 }}>{progress.phases[0].title}</div>}
          {running && <div className="loading-track" style={{ marginTop: 8 }}><div className="loading-bar" /></div>}
        </div>
        <div className="timeline">
          {!progress.groups.length && <div className="muted">领域 Agent 的思考、行动和观察会显示在这里。</div>}
          {progress.groups.map((group) => (
            <section className="react-group" key={group.agent}>
              <header className="react-head">
                <strong>{group.label}</strong>
                <span className="muted">
                  {group.status || "进行中"}
                  {group.level ? ` · ${group.level}` : ""}
                </span>
              </header>
              {group.steps.map((step) => (
                <div className={`react-step ${step.kind}`} key={`${step.kind}-${step.seq}`}>
                  <span className={`react-tag ${step.kind}${step.ok === false ? " bad" : ""}`}>
                    {step.kind === "thought" ? "思考" : step.kind === "action" ? "行动" : step.kind === "observe" ? "观察" : "结论"}
                  </span>
                  <div>{step.title}</div>
                </div>
              ))}
            </section>
          ))}
        </div>
      </aside>
    </div>
  );
}
