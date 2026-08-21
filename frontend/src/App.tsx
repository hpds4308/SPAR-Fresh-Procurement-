import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./features/auth/AuthContext";
import LoginPage from "./features/auth/LoginPage";
import ProtectedRoute from "./features/auth/ProtectedRoute";
import AdminDashboard from "./features/admin/AdminDashboard";
import BranchDashboard from "./features/branch/BranchDashboard";
import SupplierDashboard from "./features/supplier/SupplierDashboard";
import { PageSpinner } from "./features/shared/ui/PageSpinner";

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) {
    return <PageSpinner />;
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "ADMIN") return <Navigate to="/admin" replace />;
  if (user.role === "BRANCH") return <Navigate to="/branch" replace />;
  if (user.role === "SUPPLIER") return <Navigate to="/supplier" replace />;
  return <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/admin"
        element={
          <ProtectedRoute allowedRoles={["ADMIN"]}>
            <AdminDashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/branch"
        element={
          <ProtectedRoute allowedRoles={["BRANCH"]}>
            <BranchDashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/supplier"
        element={
          <ProtectedRoute allowedRoles={["SUPPLIER"]}>
            <SupplierDashboard />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
