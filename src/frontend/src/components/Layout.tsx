import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { getHealth } from "../api/client";
import { ERP_NAV, NAV_PRIMARY } from "../erpCatalog";

export default function Layout() {
  const location = useLocation();
  const erpOpen = location.pathname.startsWith("/erp/");
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [erpExpanded, setErpExpanded] = useState(erpOpen);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth({ ok: false }));
  }, []);
  useEffect(() => {
    if (erpOpen) setErpExpanded(true);
  }, [erpOpen]);

  const erpOk = Boolean((health as { erp?: { ok?: boolean }; ok?: boolean } | null)?.erp?.ok ?? (health as { ok?: boolean } | null)?.ok);
  const llmOk = Boolean((health as { llm?: { ok?: boolean } } | null)?.llm?.ok);
  const model = String((health as { llm?: { model?: string } } | null)?.llm?.model || "");

  return (
    <div className="shell">
      <aside className="sider">
        <div className="brand">
          <h1>Finprobe</h1>
          <p>采购到付款风控工作台</p>
        </div>
        <nav className="nav">
          {NAV_PRIMARY.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => {
                if (item.to === "/" && location.pathname.startsWith("/investigate")) return "active";
                return isActive ? "active" : undefined;
              }}
            >
              {item.label}
            </NavLink>
          ))}
          <button
            type="button"
            className={`nav-group ${erpOpen ? "active" : ""}`}
            onClick={() => setErpExpanded((v) => !v)}
          >
            <span>{ERP_NAV.label}</span>
            <span className="caret">{erpExpanded ? "▾" : "▸"}</span>
          </button>
          {erpExpanded && (
            <div className="nav-sub">
              {ERP_NAV.children.map((item) => (
                <NavLink key={item.to} to={item.to}>
                  {item.label}
                </NavLink>
              ))}
            </div>
          )}
        </nav>
        <div className="sider-foot">本地 Mock ERP · 127.0.0.1</div>
      </aside>
      <div className="content">
        <header className="topbar">
          <div className="muted">企业内部风控调查与复审</div>
          <div className="dots">
            <span><i className={`dot ${erpOk ? "ok" : "bad"}`} />ERP</span>
            <span><i className={`dot ${erpOk ? "ok" : "bad"}`} />MCP</span>
            <span><i className={`dot ${llmOk ? "ok" : "warn"}`} />LLM {model}</span>
          </div>
        </header>
        <div className="main-outlet">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
