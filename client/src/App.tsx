import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/auth';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import LoadsPage from './pages/LoadsPage';
import DriversPage from './pages/DriversPage';
import DispatchBoardPage from './pages/DispatchBoardPage';
import AIAssistantPage from './pages/AIAssistantPage';
import DocumentsPage from './pages/DocumentsPage';
import ReportsPage from './pages/ReportsPage';
import TenantsPage from './pages/TenantsPage';
import LoadBoardPage from './pages/LoadBoardPage';
import SettingsPage from './pages/SettingsPage';

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="dispatch" element={<DispatchBoardPage />} />
          <Route path="loads" element={<LoadsPage />} />
          <Route path="drivers" element={<DriversPage />} />
          <Route path="loadboard" element={<LoadBoardPage />} />
          <Route path="ai-assistant" element={<AIAssistantPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="tenants" element={<TenantsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
