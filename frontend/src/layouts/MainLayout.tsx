import { useState } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Button, Typography } from "antd";
import {
  HomeOutlined,
  PlayCircleOutlined,
  TeamOutlined,
  SettingOutlined,
  LogoutOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { getUser, logout } from "../services/auth";

const { Sider, Content } = Layout;
const { Text } = Typography;

const menuItems = [
  { key: "/", icon: <HomeOutlined />, label: "首页" },
  { key: "/game", icon: <PlayCircleOutlined />, label: "游戏" },
  { key: "/roles", icon: <TeamOutlined />, label: "人物" },
  { key: "/settings", icon: <SettingOutlined />, label: "设置" },
];

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const user = getUser();

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        style={{ background: "#141414", display: "flex", flexDirection: "column" }}
      >
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderBottom: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <span
            style={{
              color: "#fff",
              fontSize: collapsed ? 20 : 18,
              fontWeight: 700,
              whiteSpace: "nowrap",
              overflow: "hidden",
            }}
          >
            {collapsed ? "🐺" : "🐺 AI狼人杀"}
          </span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ background: "#141414", borderRight: 0, flex: 1 }}
        />
        {/* 用户信息 + 登出 */}
        <div
          style={{
            padding: collapsed ? "12px 8px" : "12px 16px",
            borderTop: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          {!collapsed && user && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 8,
              }}
            >
              <UserOutlined style={{ color: "rgba(255,255,255,0.5)", fontSize: 14 }} />
              <Text
                ellipsis
                style={{ color: "rgba(255,255,255,0.7)", fontSize: 13, flex: 1 }}
              >
                {user.username}
              </Text>
            </div>
          )}
          <Button
            type="text"
            icon={<LogoutOutlined />}
            onClick={handleLogout}
            block
            size={collapsed ? "middle" : "small"}
            style={{
              color: "rgba(255,255,255,0.5)",
              justifyContent: collapsed ? "center" : "flex-start",
            }}
          >
            {collapsed ? "" : "退出登录"}
          </Button>
        </div>
      </Sider>
      <Layout>
        <Content
          style={{
            background: "#fafafa",
            padding: 24,
            minHeight: "100vh",
            overflow: "auto",
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
