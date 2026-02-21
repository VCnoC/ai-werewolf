import { Badge, Card, Col, Row, Tag, Tooltip } from "antd";
import {
  UserOutlined,
  CrownOutlined,
  StopOutlined,
} from "@ant-design/icons";
import type { PlayerInfo } from "../services/websocket";

// 角色中文名映射
const ROLE_NAMES: Record<string, string> = {
  seer: "预言家",
  witch: "女巫",
  hunter: "猎人",
  guard: "守卫",
  villager: "村民",
  werewolf: "狼人",
};

// 阵营颜色
const FACTION_COLORS: Record<string, string> = {
  好人阵营: "#52c41a",
  狼人阵营: "#f5222d",
};

// 死因中文
const DEATH_CAUSE_NAMES: Record<string, string> = {
  wolf_kill: "被狼杀",
  poison: "被毒杀",
  vote_exile: "被放逐",
  hunter_shot: "被猎杀",
  wolf_explode: "自爆",
};

interface Props {
  players: Record<string, PlayerInfo>;
  thinkingPlayers: number[];
  sheriff: number | null;
  deadPlayers?: { player_id: number; cause: string; round: number }[];
  configMap?: Record<number, string>;
}

export default function PlayerPanel({
  players,
  thinkingPlayers,
  sheriff,
  deadPlayers = [],
  configMap = {},
}: Props) {
  const deadMap = new Map(deadPlayers.map((d) => [d.player_id, d]));

  return (
    <Row gutter={[8, 8]}>
      {Array.from({ length: 12 }, (_, i) => {
        const pid = i + 1;
        const pidStr = String(pid);
        const player = players[pidStr];
        const dead = deadMap.get(pid);
        const isAlive = player?.is_alive ?? true;
        const isSheriff = player?.is_sheriff || sheriff === pid;
        const isThinking = thinkingPlayers.includes(pid);

        return (
          <Col key={pid} span={4}>
            <Badge.Ribbon
              text={isSheriff ? "警长" : ""}
              color="gold"
              style={{ display: isSheriff ? undefined : "none" }}
            >
              <Card
                size="small"
                style={{
                  opacity: isAlive ? 1 : 0.45,
                  borderColor: isThinking ? "#1890ff" : undefined,
                  borderWidth: isThinking ? 2 : 1,
                }}
                styles={{
                  body: { padding: "8px 12px", textAlign: "center" },
                }}
              >
                <div style={{ fontSize: 24, marginBottom: 4 }}>
                  {isAlive ? (
                    isSheriff ? (
                      <CrownOutlined style={{ color: "#faad14" }} />
                    ) : (
                      <UserOutlined />
                    )
                  ) : (
                    <StopOutlined style={{ color: "#999" }} />
                  )}
                </div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                  {pid}号
                  {isThinking && (
                    <span
                      style={{
                        display: "inline-block",
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: "#1890ff",
                        marginLeft: 4,
                        animation: "pulse 1s infinite",
                      }}
                    />
                  )}
                </div>
                {player && (
                  <>
                    <Tag
                      color={FACTION_COLORS[player.faction] || "default"}
                      style={{ marginBottom: 2 }}
                    >
                      {ROLE_NAMES[player.role] || player.role}
                    </Tag>
                    {player.llm_config_id && configMap[player.llm_config_id] && (
                      <Tooltip title={configMap[player.llm_config_id]}>
                        <div
                          style={{
                            fontSize: 10,
                            color: "#8c8c8c",
                            marginTop: 2,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {configMap[player.llm_config_id]}
                        </div>
                      </Tooltip>
                    )}
                    {!isAlive && dead && (
                      <Tooltip
                        title={`第${dead.round}轮 ${DEATH_CAUSE_NAMES[dead.cause] || dead.cause}`}
                      >
                        <div
                          style={{ fontSize: 11, color: "#999", marginTop: 2 }}
                        >
                          {DEATH_CAUSE_NAMES[dead.cause] || dead.cause}
                        </div>
                      </Tooltip>
                    )}
                  </>
                )}
              </Card>
            </Badge.Ribbon>
          </Col>
        );
      })}
    </Row>
  );
}
