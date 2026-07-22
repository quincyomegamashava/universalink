import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type UsageRow = {
  id: string;
  endpoint: string;
  model: string | null;
  total_tokens: number;
  latency_ms: number | null;
  status_code: number;
  created_at: string;
};

export default function UsagePage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<UsageRow[]>([]);

  useEffect(() => {
    if (!token) return;
    void api<UsageRow[]>("/api/admin/usage/recent?limit=100", {}, token).then(setRows);
  }, [token]);

  return (
    <div>
      <h1>Usage</h1>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Endpoint</th>
              <th>Model</th>
              <th>Tokens</th>
              <th>Latency</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.created_at).toLocaleString()}</td>
                <td>{r.endpoint}</td>
                <td>{r.model || "—"}</td>
                <td>{r.total_tokens}</td>
                <td>{r.latency_ms != null ? `${r.latency_ms}ms` : "—"}</td>
                <td>{r.status_code}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
