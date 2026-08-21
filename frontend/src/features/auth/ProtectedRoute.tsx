import { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { PageSpinner } from "../shared/ui/PageSpinner";

export default function ProtectedRoute({
  children,
  allowedRoles,
}: {
  children: ReactNode;
  allowedRoles: string[];
}) {
  const { user, loading } = useAuth();

  if (loading) {
    return <PageSpinner />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(user.role)) {
    // Logged in, but wrong role for this route — send them to their own dashboard.
    const fallback = user.role === "ADMIN" ? "/admin" : user.role === "BRANCH" ? "/branch" : "/supplier";
    return <Navigate to={fallback} replace />;
  }

  return <>{children}</>;
}
