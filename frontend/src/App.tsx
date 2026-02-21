import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { App as AntdApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import MainLayout from "./layouts/MainLayout";
import Dashboard from "./pages/Dashboard";
import GameSetup from "./pages/GameSetup";
import RoleGuide from "./pages/RoleGuide";
import LLMConfig from "./pages/LLMConfig";
import GameWatch from "./pages/GameWatch";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ProtectedRoute from "./components/ProtectedRoute";

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#1a1a1a",
          colorBgContainer: "#ffffff",
          colorBgLayout: "#fafafa",
          colorText: "#1a1a1a",
          colorTextSecondary: "#8c8c8c",
          colorBorder: "#e8e8e8",
          borderRadius: 8,
        },
        components: {
          Menu: {
            darkItemBg: "#141414",
            darkSubMenuItemBg: "#141414",
            darkItemSelectedBg: "rgba(255,255,255,0.12)",
          },
          Button: {
            primaryColor: "#ffffff",
          },
        },
      }}
    >
      <AntdApp>
        <BrowserRouter>
        <Routes>
          {/* 登录/注册页面（独立布局） */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          {/* 带侧边栏的主布局（需要登录） */}
          <Route element={<ProtectedRoute />}>
            <Route element={<MainLayout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/game" element={<GameSetup />} />
              <Route path="/roles" element={<RoleGuide />} />
              <Route path="/settings" element={<LLMConfig />} />
            </Route>
          </Route>
          {/* 旧路由兼容重定向 */}
          <Route path="/config" element={<Navigate to="/settings" replace />} />
          <Route path="/setup" element={<Navigate to="/game" replace />} />
          {/* 观战页面独立全屏布局（公开访问） */}
          <Route path="/game/:gameId" element={<GameWatch />} />
        </Routes>
      </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  );
}

export default App;
