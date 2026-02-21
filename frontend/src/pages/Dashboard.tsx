import { useNavigate } from "react-router-dom";
import { Typography, Card, Row, Col, Button, Space } from "antd";
import {
  PlayCircleOutlined,
  TeamOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

const { Title, Paragraph, Text } = Typography;

const ROLE_COUNT = 6;
const PLAYER_COUNT = 12;

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div style={{ maxWidth: 960, margin: "0 auto" }}>
      {/* 标题区 */}
      <div style={{ textAlign: "center", marginBottom: 48, marginTop: 32 }}>
        <Title level={1} style={{ marginBottom: 8, color: "#1a1a1a" }}>
          🐺 AI 狼人杀
        </Title>
        <Paragraph
          style={{ fontSize: 16, color: "#8c8c8c", marginBottom: 32 }}
        >
          12 名 AI 玩家，6 种角色，全自动推理对局
        </Paragraph>
        <Button
          type="primary"
          size="large"
          icon={<ThunderboltOutlined />}
          onClick={() => navigate("/game")}
          style={{
            height: 48,
            paddingInline: 32,
            fontSize: 16,
            background: "#1a1a1a",
            borderColor: "#1a1a1a",
          }}
        >
          快速开始
        </Button>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={8}>
          <Card
            hoverable
            onClick={() => navigate("/roles")}
            style={{ textAlign: "center", cursor: "pointer" }}
          >
            <TeamOutlined
              style={{ fontSize: 32, color: "#1a1a1a", marginBottom: 12 }}
            />
            <Title level={3} style={{ margin: 0 }}>
              {ROLE_COUNT}
            </Title>
            <Text type="secondary">角色种类</Text>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card
            hoverable
            onClick={() => navigate("/game")}
            style={{ textAlign: "center", cursor: "pointer" }}
          >
            <PlayCircleOutlined
              style={{ fontSize: 32, color: "#1a1a1a", marginBottom: 12 }}
            />
            <Title level={3} style={{ margin: 0 }}>
              {PLAYER_COUNT}
            </Title>
            <Text type="secondary">AI 玩家</Text>
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card
            hoverable
            onClick={() => navigate("/settings")}
            style={{ textAlign: "center", cursor: "pointer" }}
          >
            <SettingOutlined
              style={{ fontSize: 32, color: "#1a1a1a", marginBottom: 12 }}
            />
            <Title level={3} style={{ margin: 0 }}>
              LLM
            </Title>
            <Text type="secondary">模型配置</Text>
          </Card>
        </Col>
      </Row>

      {/* 快速导航 */}
      <Card style={{ marginTop: 24 }}>
        <Title level={4}>快速导航</Title>
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <div>
            <Text strong>🎮 游戏</Text>
            <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
              配置 12 名 AI 玩家的 LLM 模型，开始一局全自动狼人杀对局
            </Paragraph>
          </div>
          <div>
            <Text strong>👥 人物</Text>
            <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
              查看预言家、女巫、猎人、守卫、村民、狼人的技能介绍
            </Paragraph>
          </div>
          <div>
            <Text strong>⚙️ 设置</Text>
            <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
              管理 LLM API 配置，支持多模型切换
            </Paragraph>
          </div>
        </Space>
      </Card>
    </div>
  );
}
