import { Card, Tabs, Tag, Typography, Empty } from "antd";
import type { NightActionData, PlayerInfo } from "../services/websocket";

export const ROLE_NAMES: Record<string, string> = {
  seer: "预言家",
  witch: "女巫",
  hunter: "猎人",
  guard: "守卫",
  villager: "村民",
  werewolf: "狼人",
};

// 频道配置
export const CHANNELS = [
  { key: "guard", label: "🛡️ 守卫", color: "#52c41a" },
  { key: "wolf", label: "🐺 狼人", color: "#f5222d" },
  { key: "witch", label: "🧪 女巫", color: "#722ed1" },
  { key: "seer", label: "👁️ 预言家", color: "#1890ff" },
  { key: "resolve", label: "⚙️ 结算", color: "#faad14" },
];

/** 按频道过滤夜晚行动 */
export function getChannelActions(actions: NightActionData[], channel: string): NightActionData[] {
  if (channel === "resolve") {
    return actions.filter(
      (a) => !a.channel || a.channel === "resolve" || a.detail
    );
  }
  if (channel === "wolf") {
    return actions.filter((a) => a.channel === "wolf" || a.channel === "wolf_discussion");
  }
  return actions.filter((a) => a.channel === channel);
}

/** 渲染 AI 思考笔记 */
export function renderAiNotes(action: NightActionData, showThinking = true) {
  if (!showThinking) return null;
  if (!action.ai_notes) return null;
  if (typeof action.ai_notes === "string") {
    return (
      <div
        style={{
          color: "#8c8c8c",
          fontStyle: "italic",
          fontSize: 12,
          marginTop: 2,
          marginBottom: 4,
          paddingLeft: 8,
          borderLeft: "2px solid #d9d9d9",
        }}
      >
        🧠 {action.ai_notes}
      </div>
    );
  }
  // Record<number, string> — 多人（狼人频道）
  return (
    <div style={{ marginTop: 2, marginBottom: 4 }}>
      {Object.entries(action.ai_notes).map(([pid, note]) => (
        <div
          key={pid}
          style={{
            color: "#8c8c8c",
            fontStyle: "italic",
            fontSize: 12,
            paddingLeft: 8,
            borderLeft: "2px solid #d9d9d9",
            marginBottom: 2,
          }}
        >
          🧠 {pid}号: {note}
        </div>
      ))}
    </div>
  );
}

/** 渲染单个夜晚行动 */
export function renderAction(
  action: NightActionData,
  idx: number,
  players: Record<string, PlayerInfo>,
) {
  const pid = action.player_id;
  const player = pid ? players[String(pid)] : null;
  const roleName = player ? ROLE_NAMES[player.role] || player.role : "";

  switch (action.channel) {
    case "guard":
      return (
        <div key={idx} style={{ marginBottom: 8 }}>
          <Tag color="green">守护</Tag>
          <Typography.Text>
            {pid}号({roleName}) 守护了{" "}
            <Typography.Text strong>{action.target}号</Typography.Text>
          </Typography.Text>
        </div>
      );

    case "wolf_discussion":
      return (
        <div key={idx} style={{ marginBottom: 8 }}>
          <Tag color="volcano">第{(action as NightActionData & { discussion_round?: number }).discussion_round}轮</Tag>
          <Typography.Text>
            {pid}号(狼人) 建议刀{" "}
            <Typography.Text strong>{action.target}号</Typography.Text>
          </Typography.Text>
          {(action as NightActionData & { speech?: string }).speech && (
            <div
              style={{
                color: "#8c8c8c",
                fontSize: 12,
                marginTop: 2,
                paddingLeft: 8,
                borderLeft: "2px solid #f5222d",
              }}
            >
              💬 {(action as NightActionData & { speech?: string }).speech}
            </div>
          )}
        </div>
      );

    case "wolf":
      return (
        <div key={idx} style={{ marginBottom: 8 }}>
          <Tag color="red">击杀</Tag>
          <Typography.Text>
            狼人团队({action.player_ids?.join("、")}号) 决定刀{" "}
            <Typography.Text strong>{action.target}号</Typography.Text>
          </Typography.Text>
        </div>
      );

    case "witch": {
      const parts: string[] = [];
      if (action.victim !== undefined) {
        parts.push(
          action.victim !== null
            ? `看到${action.victim}号被刀`
            : "今晚无人被刀"
        );
      }
      if (action.save) parts.push("使用解药救人");
      if (action.poison_target)
        parts.push(`使用毒药毒杀${action.poison_target}号`);
      if (!action.save && !action.poison_target && parts.length <= 1)
        parts.push("未使用药物");

      return (
        <div key={idx} style={{ marginBottom: 8 }}>
          <Tag color="purple">女巫</Tag>
          <Typography.Text>
            {pid}号({roleName}): {parts.join("，")}
          </Typography.Text>
        </div>
      );
    }

    case "seer":
      return (
        <div key={idx} style={{ marginBottom: 8 }}>
          <Tag color="blue">查验</Tag>
          <Typography.Text>
            {pid}号({roleName}) 查验了{action.target}号 →{" "}
            <Typography.Text
              strong
              style={{
                color: action.result === "狼人" ? "#f5222d" : "#52c41a",
              }}
            >
              {action.result}
            </Typography.Text>
          </Typography.Text>
        </div>
      );

    default:
      // 结算事件
      if (action.detail) {
        const detailText: Record<string, string> = {
          guard_blocked: `守卫守住了${action.wolf_target}号`,
          wolf_empty_knife: "狼人选择空刀",
          witch_saved: "女巫救人成功",
          witch_poisoned: `女巫毒杀了${action.target}号`,
          peaceful_night: "平安夜，无人死亡",
        };
        return (
          <div key={idx} style={{ marginBottom: 8 }}>
            <Tag color="orange">结算</Tag>
            <Typography.Text>
              {detailText[action.detail] || action.detail}
            </Typography.Text>
          </div>
        );
      }
      if (action.type === "death") {
        return (
          <div key={idx} style={{ marginBottom: 8 }}>
            <Tag color="red">死亡</Tag>
            <Typography.Text>
              {action.player_id}号玩家死亡（{String(action.cause ?? "")}）
            </Typography.Text>
          </div>
        );
      }
      return null;
  }
}

// ========== NightPanel 组件 ==========

interface Props {
  round: number;
  actions: NightActionData[];
  players: Record<string, PlayerInfo>;
  thinkingPlayers: number[];
  showThinking?: boolean;
}

export default function NightPanel({
  round,
  actions,
  players,
  thinkingPlayers,
  showThinking = true,
}: Props) {
  const tabItems = CHANNELS.map((ch) => {
    const channelActions = getChannelActions(actions, ch.key);
    const isThinking =
      ch.key === "wolf"
        ? thinkingPlayers.some((id) => {
            const p = players[String(id)];
            return p?.role === "werewolf";
          })
        : thinkingPlayers.some((id) => {
            const p = players[String(id)];
            return p?.role === ch.key;
          });

    return {
      key: ch.key,
      label: (
        <span>
          {ch.label}
          {isThinking && (
            <span
              style={{
                display: "inline-block",
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "#1890ff",
                marginLeft: 4,
                animation: "pulse 1s infinite",
              }}
            />
          )}
        </span>
      ),
      children:
        channelActions.length > 0 ? (
          <div style={{ padding: "8px 0" }}>
            {channelActions.map((a, i) => (
              <div key={i}>
                {renderAction(a, i, players)}
                {renderAiNotes(a, showThinking)}
              </div>
            ))}
          </div>
        ) : (
          <Empty
            description={isThinking ? "思考中..." : "等待行动"}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ),
    };
  });

  return (
    <Card
      title={`🌙 第${round}夜`}
      size="small"
      style={{ marginBottom: 16 }}
    >
      <Tabs items={tabItems} size="small" />
    </Card>
  );
}
