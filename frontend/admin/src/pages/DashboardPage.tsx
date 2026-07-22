import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type Stats = { users: number; api_keys: number; chats: number };
type Usage = { total_requests: number; total_tokens: number; prompt_tokens: number; completion_tokens: number };
type Health = { status: string; components: { name: string; status: string }[] };

export default function DashboardPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<Stats | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    if (!token) return;
    void Promise.all([
      api<Stats>("/api/admin/stats", {}, token).then(setStats),
      api<Usage>("/api/admin/usage/summary", {}, token).then(setUsage),
      api<Health>("/api/admin/health", {}, token).then(setHealth),
    ]);
  }, [token]);

  return (
    <div>
      <h1>Dashboard</h1>
      <div className="grid-stats">
        <div className="stat">
          <div className="label">Users</div>
          <div className="value">{stats?.users ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="label">API keys</div>
          <div className="value">{stats?.api_keys ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="label">Chats</div>
          <div className="value">{stats?.chats ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="label">Total tokens</div>
          <div className="value">{usage?.total_tokens ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="label">Requests</div>
          <div className="value">{usage?.total_requests ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="label">System</div>
          <div className="value" style={{ fontSize: "1.1rem" }}>
            {health?.status ?? "—"}
          </div>
        </div>
      </div>
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Service health</h2>
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(health?.components || []).map((c) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td>
                  <span className={`badge ${c.status === "ok" ? "ok" : "err"}`}>{c.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
