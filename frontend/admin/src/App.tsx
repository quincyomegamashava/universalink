import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import UsersPage from "./pages/UsersPage";
import ModelsPage from "./pages/ModelsPage";
import UsagePage from "./pages/UsagePage";
import SettingsPage from "./pages/SettingsPage";
import ToolsPage from "./pages/ToolsPage";
import RagPage from "./pages/RagPage";
import HealthPage from "./pages/HealthPage";

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          AI Platform
          <span>Admin Console · {user?.email}</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/users">Users</NavLink>
          <NavLink to="/models">Models</NavLink>
          <NavLink to="/usage">Usage</NavLink>
          <NavLink to="/rag">RAG</NavLink>
          <NavLink to="/tools">Agent Tools</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <NavLink to="/health">Health</NavLink>
        </nav>
        <button className="btn secondary" onClick={logout}>
          Sign out
        </button>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

function Private({ children }: { children: React.ReactNode }) {
  const { token, user } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (token && !user) return <div className="content">Loading…</div>;
  if (user && user.role !== "admin") return <Navigate to="/login" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Private>
            <DashboardPage />
          </Private>
        }
      />
      <Route
        path="/users"
        element={
          <Private>
            <UsersPage />
          </Private>
        }
      />
      <Route
        path="/models"
        element={
          <Private>
            <ModelsPage />
          </Private>
        }
      />
      <Route
        path="/usage"
        element={
          <Private>
            <UsagePage />
          </Private>
        }
      />
      <Route
        path="/rag"
        element={
          <Private>
            <RagPage />
          </Private>
        }
      />
      <Route
        path="/tools"
        element={
          <Private>
            <ToolsPage />
          </Private>
        }
      />
      <Route
        path="/settings"
        element={
          <Private>
            <SettingsPage />
          </Private>
        }
      />
      <Route
        path="/health"
        element={
          <Private>
            <HealthPage />
          </Private>
        }
      />
    </Routes>
  );
}
