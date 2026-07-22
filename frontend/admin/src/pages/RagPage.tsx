import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type Collection = {
  id: string;
  name: string;
  description: string | null;
  qdrant_collection: string;
  is_active: boolean;
  created_at: string;
};

export default function RagPage() {
  const { token } = useAuth();
  const [collections, setCollections] = useState<Collection[]>([]);

  useEffect(() => {
    if (!token) return;
    void api<Collection[]>("/api/rag/admin/collections", {}, token).then(setCollections);
  }, [token]);

  return (
    <div>
      <h1>RAG collections</h1>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Qdrant collection</th>
              <th>Active</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {collections.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>
                  <code>{c.qdrant_collection}</code>
                </td>
                <td>
                  <span className={`badge ${c.is_active ? "ok" : "err"}`}>{c.is_active ? "yes" : "no"}</span>
                </td>
                <td>{new Date(c.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {collections.length === 0 && <p style={{ color: "var(--muted)" }}>No collections yet. Users create them via `/api/rag/collections`.</p>}
      </div>
    </div>
  );
}
