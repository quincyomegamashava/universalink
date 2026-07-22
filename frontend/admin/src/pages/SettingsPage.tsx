import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type Setting = { key: string; value: Record<string, unknown>; description: string | null };

export default function SettingsPage() {
  const { token } = useAuth();
  const [settings, setSettings] = useState<Setting[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    if (!token) return;
    setSettings(await api<Setting[]>("/api/admin/settings", {}, token));
  }

  useEffect(() => {
    void load();
  }, [token]);

  async function save(key: string, raw: string) {
    if (!token) return;
    setMessage(null);
    try {
      const value = JSON.parse(raw);
      await api("/api/admin/settings", { method: "PUT", body: JSON.stringify({ key, value }) }, token);
      setMessage(`Saved ${key}`);
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed");
    }
  }

  return (
    <div>
      <h1>Settings</h1>
      {message && <p>{message}</p>}
      <div className="panel">
        {settings.map((s) => (
          <div key={s.key} style={{ marginBottom: "1.25rem" }}>
            <strong>{s.key}</strong>
            {s.description && <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{s.description}</div>}
            <textarea
              defaultValue={JSON.stringify(s.value, null, 2)}
              rows={4}
              style={{
                width: "100%",
                marginTop: "0.5rem",
                background: "var(--bg)",
                color: "var(--text)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "0.75rem",
                fontFamily: "var(--mono)",
              }}
              id={`setting-${s.key}`}
            />
            <button
              className="btn"
              style={{ marginTop: "0.5rem" }}
              onClick={() => {
                const el = document.getElementById(`setting-${s.key}`) as HTMLTextAreaElement;
                void save(s.key, el.value);
              }}
            >
              Save
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
