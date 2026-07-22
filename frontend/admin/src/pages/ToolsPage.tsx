import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type Tool = { tool_name: string; role: string; enabled: boolean; config: Record<string, unknown> };

export default function ToolsPage() {
  const { token } = useAuth();
  const [tools, setTools] = useState<Tool[]>([]);

  async function load() {
    if (!token) return;
    setTools(await api<Tool[]>("/api/admin/tools", {}, token));
  }

  useEffect(() => {
    void load();
  }, [token]);

  async function toggle(t: Tool) {
    if (!token) return;
    await api(
      `/api/admin/tools/${t.tool_name}/${t.role}`,
      { method: "PATCH", body: JSON.stringify({ enabled: !t.enabled }) },
      token
    );
    await load();
  }

  return (
    <div>
      <h1>Agent tools</h1>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Tool</th>
              <th>Role</th>
              <th>Enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tools.map((t) => (
              <tr key={`${t.tool_name}-${t.role}`}>
                <td>{t.tool_name}</td>
                <td>{t.role}</td>
                <td>
                  <span className={`badge ${t.enabled ? "ok" : "err"}`}>{t.enabled ? "on" : "off"}</span>
                </td>
                <td>
                  <button className="btn secondary" onClick={() => toggle(t)}>
                    Toggle
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
