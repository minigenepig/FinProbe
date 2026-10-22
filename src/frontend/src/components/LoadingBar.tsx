export function LoadingBar({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="loading-block">
      <div className="loading-track" aria-hidden="true">
        <div className="loading-bar" />
      </div>
      <div className="muted">{label}</div>
    </div>
  );
}
