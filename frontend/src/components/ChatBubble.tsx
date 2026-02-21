import { Avatar, Typography } from "antd";
import { UserOutlined } from "@ant-design/icons";

const ROLE_NAMES: Record<string, string> = {
  seer: "预言家",
  witch: "女巫",
  hunter: "猎人",
  guard: "守卫",
  villager: "村民",
  werewolf: "狼人",
};

const FACTION_COLORS: Record<string, string> = {
  好人阵营: "#52c41a",
  狼人阵营: "#f5222d",
};

interface Props {
  playerId: number;
  content: string;
  role?: string;
  faction?: string;
  isLastWords?: boolean;
  isExplode?: boolean;
  aiNotes?: string;
  showThinking?: boolean;
  parseLevel?: number;
}

export default function ChatBubble({
  playerId,
  content,
  role,
  faction,
  isLastWords,
  isExplode,
  aiNotes,
  showThinking = true,
  parseLevel,
}: Props) {
  const roleName = role ? ROLE_NAMES[role] || role : "";
  const color = faction ? FACTION_COLORS[faction] || "#1890ff" : "#1890ff";

  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
      <Avatar
        size={40}
        icon={<UserOutlined />}
        style={{ backgroundColor: color, flexShrink: 0 }}
      >
        {playerId}
      </Avatar>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ marginBottom: 4 }}>
          <Typography.Text strong>{playerId}号</Typography.Text>
          {roleName && (
            <Typography.Text
              type="secondary"
              style={{ marginLeft: 8, fontSize: 12 }}
            >
              {roleName}
            </Typography.Text>
          )}
          {isLastWords && (
            <Typography.Text
              style={{ marginLeft: 8, fontSize: 12, color: "#8c8c8c" }}
            >
              [遗言]
            </Typography.Text>
          )}
          {isExplode && (
            <Typography.Text
              style={{ marginLeft: 8, fontSize: 12, color: "#f5222d" }}
            >
              [自爆]
            </Typography.Text>
          )}
        </div>

        {/* AI 思考（灰色斜体，可折叠） */}
        {showThinking && aiNotes && (
          <div
            style={{
              color: "#8c8c8c",
              fontStyle: "italic",
              fontSize: 13,
              marginBottom: 4,
              padding: "4px 8px",
              background: "#fafafa",
              borderRadius: 4,
              borderLeft: "3px solid #d9d9d9",
            }}
          >
            🧠 {aiNotes}
          </div>
        )}

        {/* 降级警告（parse_level >= 3 表示 regex 或随机兜底） */}
        {parseLevel !== undefined && parseLevel >= 3 && (
          <div
            style={{
              color: parseLevel >= 4 ? "#f5222d" : "#fa8c16",
              fontSize: 12,
              marginBottom: 4,
            }}
          >
            {parseLevel >= 4
              ? "⚠️ AI 输出解析完全失败，使用随机兜底"
              : "⚠️ AI 输出格式异常，使用降级解析"}
          </div>
        )}

        {/* 发言内容（对话气泡） */}
        <div
          style={{
            background: isExplode ? "#fff1f0" : "#f0f5ff",
            border: `1px solid ${isExplode ? "#ffa39e" : "#d6e4ff"}`,
            borderRadius: "4px 12px 12px 12px",
            padding: "8px 12px",
            maxWidth: "85%",
          }}
        >
          <Typography.Text>{content}</Typography.Text>
        </div>
      </div>
    </div>
  );
}
