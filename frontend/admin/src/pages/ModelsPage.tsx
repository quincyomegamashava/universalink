import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type ModelsResponse = {
  ollama: { name?: string; model?: string; size?: number }[];
};

export default function ModelsPage() {
  const { token } = useAuth();
  const [models, setModels] = useState<ModelsResponse["ollama"]>([]);
  const [name, setName] = useState("llama3.2:3b");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!token) return;
    const data = await api<ModelsResponse>("/api/admin/models", {}, token);
    setModels(data.ollama || []);
  }

  useEffect(() => {
    void load();
  }, [token]);

  async function pull(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api("/api/admin/models/pull", { method: "POST", body: JSON.stringify({ name }) }, token);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pull failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(modelName: string) {
    if (!token) return;
    if (!confirm(`Delete model ${modelName}?`)) return;
    await api(`/api/admin/models/${encodeURIComponent(modelName)}`, { method: "DELETE" }, token);
    await load();
  }

  return (
    <div>
      <h1>Models</h1>
      <div className="panel" style={{ marginBottom: "1rem" }}>
        <form className="row-actions" onSubmit={pull}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="ollama model tag" required />
          <button className="btn" disabled={busy}>
            {busy ? "Pulling…" : "Pull model"}
          </button>
        </form>
        {error && <div className="error">{error}</div>}
      </div>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {models.map((m) => {
              const n = m.name || m.model || "unknown";
              return (
                <tr key={n}>
                  <td>{n}</td>
                  <td>{m.size ? `${Math.round(m.size / 1e9)} GB` : "—"}</td>
                  <td>
                    <button className="btn danger" onClick={() => remove(n)}>
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
