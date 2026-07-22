import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type Health = {
  status: string;
  components: { name: string; status: string; detail?: string | null }[];
};

export default function HealthPage() {
  const { token } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    if (!token) return;
    const tick = () => void api<Health>("/api/admin/health", {}, token).then(setHealth);
    tick();
    const id = setInterval(tick, 15000);
    return () => clearInterval(id);
  }, [token]);

  return (
    <div>
      <h1>Health & ops</h1>
      <div className="panel">
        <p>
          Overall: <span className={`badge ${health?.status === "ok" ? "ok" : "err"}`}>{health?.status ?? "…"}</span>
        </p>
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {(health?.components || []).map((c) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td>
                  <span className={`badge ${c.status === "ok" ? "ok" : "err"}`}>{c.status}</span>
                </td>
                <td>{c.detail || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ color: "var(--muted)", marginTop: "1.25rem" }}>
          Prometheus scrapes <code>/metrics</code> when the monitoring profile is enabled. See{" "}
          <code>docs/phase-8-production.md</code>.
        </p>
      </div>
    </div>
  );
}
