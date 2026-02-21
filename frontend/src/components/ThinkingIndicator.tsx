import { Spin, Typography } from "antd";
import { LoadingOutlined } from "@ant-design/icons";

const PHASE_NAMES: Record<string, string> = {
  guard: "守卫行动",
  wolf: "狼人商量",
  witch: "女巫决策",
  seer: "预言家查验",
  discussion: "发言",
  vote: "投票",
  last_words: "遗言",
  hunter_shoot: "猎人开枪",
  sheriff_register: "上警决定",
  sheriff_speech: "竞选演说",
  sheriff_vote: "警长投票",
  sheriff_adjust_order: "调整发言顺序",
};

interface Props {
  playerIds: number[];
  phase: string;
}

export default function ThinkingIndicator({ playerIds, phase }: Props) {
  if (playerIds.length === 0) return null;

  const phaseName = PHASE_NAMES[phase] || phase;
  const playerText =
    playerIds.length === 1
      ? `${playerIds[0]}号玩家`
      : `${playerIds.join("、")}号玩家`;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 16px",
        margin: "8px 0",
        background: "#e6f7ff",
        border: "1px solid #91d5ff",
        borderRadius: 8,
      }}
    >
      <Spin indicator={<LoadingOutlined spin />} size="small" />
      <Typography.Text style={{ color: "#096dd9" }}>
        {playerText}正在{phaseName}中...
      </Typography.Text>
    </div>
  );
}
