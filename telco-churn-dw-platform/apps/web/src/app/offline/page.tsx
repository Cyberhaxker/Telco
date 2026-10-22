export default function OfflinePage() {
  return (
    <div className="login">
      <div className="panel card">
        <h1>This page is not available offline yet</h1>
        <p className="muted">Open it once while online and it will be saved on this device. Data you already viewed is still available from the dashboard.</p>
        <a className="btn primary" href="/dashboard">Go to dashboard</a>
      </div>
    </div>
  );
}
