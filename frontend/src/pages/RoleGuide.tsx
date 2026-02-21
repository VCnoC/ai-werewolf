import { Typography, Card, Row, Col, Tag, Space } from "antd";

const { Title, Paragraph, Text } = Typography;

interface RoleInfo {
  name: string;
  faction: "good" | "wolf";
  factionLabel: string;
  emoji: string;
  description: string;
  skills: string[];
  count: number;
}

const roles: RoleInfo[] = [
  {
    name: "预言家",
    faction: "good",
    factionLabel: "好人阵营",
    emoji: "🔮",
    description: "拥有验人能力的核心角色，每晚可以查验一名玩家的身份。",
    skills: ["每晚选择一名玩家查验其阵营（好人/狼人）"],
    count: 1,
  },
  {
    name: "女巫",
    faction: "good",
    factionLabel: "好人阵营",
    emoji: "🧪",
    description: "拥有一瓶解药和一瓶毒药的强力角色。",
    skills: [
      "解药：救活当晚被狼人杀害的玩家（全局仅一次）",
      "毒药：毒杀一名玩家（全局仅一次）",
      "同一晚不能同时使用解药和毒药",
    ],
    count: 1,
  },
  {
    name: "猎人",
    faction: "good",
    factionLabel: "好人阵营",
    emoji: "🔫",
    description: "死亡时可以开枪带走一名玩家的复仇角色。",
    skills: [
      "被投票出局或被狼人杀死时，可以开枪带走一名存活玩家",
      "被女巫毒死时不能开枪",
    ],
    count: 1,
  },
  {
    name: "守卫",
    faction: "good",
    factionLabel: "好人阵营",
    emoji: "🛡️",
    description: "每晚可以守护一名玩家使其免受狼人袭击。",
    skills: [
      "每晚选择一名玩家进行守护",
      "不能连续两晚守护同一名玩家",
      "可以守护自己",
    ],
    count: 1,
  },
  {
    name: "村民",
    faction: "good",
    factionLabel: "好人阵营",
    emoji: "👤",
    description: "没有特殊能力的普通好人，依靠逻辑推理和投票参与游戏。",
    skills: ["白天参与讨论和投票", "通过分析发言推理狼人身份"],
    count: 4,
  },
  {
    name: "狼人",
    faction: "wolf",
    factionLabel: "狼人阵营",
    emoji: "🐺",
    description: "每晚可以集体袭击一名玩家，白天伪装成好人。",
    skills: [
      "夜晚与同伴商议并选择一名玩家进行袭击",
      "白天伪装成好人参与讨论和投票",
      "可以选择白天自爆（暴露身份，立即结束当天投票）",
    ],
    count: 4,
  },
];

const factionColor = { good: "#1a1a1a", wolf: "#8c8c8c" };

export default function RoleGuide() {
  const goodRoles = roles.filter((r) => r.faction === "good");
  const wolfRoles = roles.filter((r) => r.faction === "wolf");

  const renderRoleCard = (role: RoleInfo) => (
    <Col xs={24} sm={12} lg={8} key={role.name}>
      <Card
        hoverable
        style={{ height: "100%" }}
        title={
          <Space>
            <span style={{ fontSize: 20 }}>{role.emoji}</span>
            <span>{role.name}</span>
            <Tag color={factionColor[role.faction]}>{role.factionLabel}</Tag>
            {role.count > 1 && <Tag>x{role.count}</Tag>}
          </Space>
        }
      >
        <Paragraph type="secondary">{role.description}</Paragraph>
        <Text strong style={{ display: "block", marginBottom: 8 }}>
          技能：
        </Text>
        <ul style={{ paddingLeft: 20, margin: 0 }}>
          {role.skills.map((s, i) => (
            <li key={i} style={{ color: "#595959", marginBottom: 4 }}>
              {s}
            </li>
          ))}
        </ul>
      </Card>
    </Col>
  );

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <Title level={2}>角色图鉴</Title>
      <Paragraph type="secondary" style={{ marginBottom: 24 }}>
        标准 12 人局：1 预言家 + 1 女巫 + 1 猎人 + 1 守卫 + 4 村民 vs 4 狼人
      </Paragraph>

      {/* 好人阵营 */}
      <Title level={4} style={{ marginBottom: 16 }}>
        ⚔️ 好人阵营
      </Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
        {goodRoles.map(renderRoleCard)}
      </Row>

      {/* 狼人阵营 */}
      <Title level={4} style={{ marginBottom: 16 }}>
        🌑 狼人阵营
      </Title>
      <Row gutter={[16, 16]}>{wolfRoles.map(renderRoleCard)}</Row>
    </div>
  );
}
