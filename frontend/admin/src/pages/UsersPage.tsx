import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

type User = {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
};

export default function UsersPage() {
  const { token } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!token) return;
    setUsers(await api<User[]>("/api/admin/users", {}, token));
  }

  useEffect(() => {
    void load();
  }, [token]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    try {
      await api(
        "/api/admin/users",
        { method: "POST", body: JSON.stringify({ email, name, password, role }) },
        token
      );
      setEmail("");
      setName("");
      setPassword("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function toggleActive(u: User) {
    if (!token) return;
    await api(
      `/api/admin/users/${u.id}`,
      { method: "PATCH", body: JSON.stringify({ is_active: !u.is_active }) },
      token
    );
    await load();
  }

  return (
    <div>
      <h1>Users</h1>
      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>Create user</h2>
        {error && <div className="error">{error}</div>}
        <form className="row-actions" onSubmit={onCreate}>
          <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
          <input placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input
            placeholder="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
          <button className="btn" type="submit">
            Create
          </button>
        </form>
      </div>
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td>
                <td>{u.email}</td>
                <td>{u.role}</td>
                <td>
                  <span className={`badge ${u.is_active ? "ok" : "err"}`}>{u.is_active ? "yes" : "no"}</span>
                </td>
                <td>
                  <button className="btn secondary" onClick={() => toggleActive(u)}>
                    {u.is_active ? "Disable" : "Enable"}
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
