import { Navigate, Outlet } from "react-router-dom";
import { isAuthenticated } from "../services/auth";

/**
 * 路由守卫：未登录时重定向到登录页
 */
export default function ProtectedRoute() {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
