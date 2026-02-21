import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Typography,
  Layout,
  Button,
  Space,
  Tag,
  Switch,
  Result,
  Divider,
  Alert,
} from "antd";
import {
  PauseCircleOutlined,
  PlayCircleOutlined,
  ArrowLeftOutlined,
  TrophyOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
} from "@ant-design/icons";
import {
  useGameWebSocket,
  type GameLog,
  type SpeechData,
  type VoteData,
  type VoteCastData,
  type JudgeNarrationData,
  type AIThinkingData,
  type GameEndData,
  type GameErrorData,
} from "../services/websocket";
import { api } from "../services/api";
import PlayerPanel from "../components/PlayerPanel";
import ChatBubble from "../components/ChatBubble";
import JudgeNarration from "../components/JudgeNarration";
import TimelinePanel from "../components/TimelinePanel";
import VotePanel from "../components/VotePanel";
import ThinkingIndicator from "../components/ThinkingIndicator";

const PHASE_LABELS: Record<string, string> = {
  GAME_START: "游戏开始",
  NIGHT_PHASE: "🌙 夜晚",
  DAY_PHASE: "☀️ 白天",
  GAME_END: "游戏结束",
};

const WINNER_COLORS: Record<string, string> = {
  好人阵营: "#52c41a",
  狼人阵营: "#f5222d",
  平局: "#faad14",
};

export default function GameWatch() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();
  const { state, pause, resume, connectionStatus } = useGameWebSocket(gameId);
  const [showThinking, setShowThinking] = useState(true);
  const logEndRef = useRef<HTMLDivElement>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // 加载 LLM 配置列表，构建 id → model_name 映射
  const [configMap, setConfigMap] = useState<Record<number, string>>({});
  useEffect(() => {
    api.getLLMConfigs().then((configs) => {
      const map: Record<number, string> = {};
      for (const c of configs) {
        map[c.id] = c.model_name;
      }
      setConfigMap(map);
    }).catch(() => {});
  }, []);

  // 智能自动滚动：仅在用户已经在底部附近时才滚动
  useEffect(() => {
    const container = logContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
    if (isNearBottom) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [state.logs.length]);

  const renderLog = (log: GameLog) => {
    switch (log.type) {
      case "game.judge_narration": {
        const d = log.data as JudgeNarrationData;
        return <JudgeNarration key={log.id} text={d.text} />;
      }

      case "game.speech": {
        const d = log.data as SpeechData;
        const player = state.players[String(d.player_id)];
        return (
          <ChatBubble
            key={log.id}
            playerId={d.player_id}
            content={d.content}
            role={player?.role}
            faction={player?.faction}
            isLastWords={d.is_last_words}
            isExplode={d.is_explode}
            aiNotes={d.ai_notes}
            showThinking={showThinking}
            parseLevel={d._parse_level}
          />
        );
      }

      case "game.vote": {
        const d = log.data as VoteData;
        return (
          <VotePanel
            key={log.id}
            votes={d.votes}
            counts={d.counts}
            sheriff={state.sheriff}
          />
        );
      }

      case "game.vote_cast": {
        const d = log.data as VoteCastData;
        const voter = state.players[String(d.voter_id)];
        const isSheriff = d.voter_id === state.sheriff;
        return (
          <div
            key={log.id}
            style={{
              padding: "4px 12px",
              margin: "2px 0",
              fontSize: 13,
              color: "#595959",
            }}
          >
            <Tag color={isSheriff ? "gold" : "default"} style={{ fontSize: 12 }}>
              {d.voter_id}号{voter ? `(${voter.role})` : ""}
              {isSheriff ? " 👑" : ""}
            </Tag>
            {d.target ? `投票给 ${d.target}号` : "弃票"}
          </div>
        );
      }

      case "game.ai_thinking": {
        if (!showThinking) return null;
        const d = log.data as AIThinkingData;
        const ids = d.player_ids || (d.player_id ? [d.player_id] : []);
        return (
          <ThinkingIndicator key={log.id} playerIds={ids} phase={d.phase} />
        );
      }

      case "game.death": {
        // 死亡事件由法官叙述覆盖，不单独渲染
        return null;
      }

      case "game.phase_change": {
        // 阶段切换由标题区域显示
        return null;
      }

      case "game.end": {
        const d = log.data as GameEndData;
        return (
          <Result
            key={log.id}
            icon={<TrophyOutlined style={{ color: WINNER_COLORS[d.winner] }} />}
            title={`游戏结束 - ${d.winner}获胜！`}
            subTitle={`共进行了${d.round}个回合`}
            extra={
              <Button onClick={() => navigate("/setup")}>开始新游戏</Button>
            }
          />
        );
      }

      case "game.error": {
        const d = log.data as GameErrorData;
        return (
          <Alert
            key={log.id}
            type="error"
            showIcon
            title="游戏异常"
            description={d.message}
            style={{ marginBottom: 12 }}
          />
        );
      }

      case "game.sheriff_election": {
        const d = log.data as Record<string, unknown>;
        const phase = d.phase as string;

        // 每个玩家的报名决定
        if (phase === "register_decision") {
          const pid = d.player_id as number;
          const run = d.run_for_sheriff as boolean;
          return (
            <div
              key={log.id}
              style={{
                padding: "4px 12px",
                margin: "2px 0",
                fontSize: 13,
                color: "#595959",
              }}
            >
              <Tag color={run ? "gold" : "default"} style={{ fontSize: 12 }}>
                {pid}号
              </Tag>
              {run ? "决定上警 ✋" : "选择不上警"}
            </div>
          );
        }

        // 每个玩家的警长投票
        if (phase === "vote_cast") {
          const voterId = d.voter_id as number;
          const target = d.target as number | null;
          return (
            <div
              key={log.id}
              style={{
                padding: "4px 12px",
                margin: "2px 0",
                fontSize: 13,
                color: "#595959",
              }}
            >
              <Tag color="default" style={{ fontSize: 12 }}>
                {voterId}号
              </Tag>
              {target ? `投给 ${target}号` : "弃票"}
            </div>
          );
        }

        // 其他阶段（start, candidates, elected, vote_result, badge_transferred, badge_destroyed）
        const text = d.text as string | undefined;
        if (!text) return null;

        return (
          <div
            key={log.id}
            style={{
              textAlign: "center",
              padding: "12px 16px",
              margin: "8px 0",
              background: "#fffbe6",
              border: "1px solid #ffe58f",
              borderRadius: 8,
            }}
          >
            <Typography.Text strong style={{ color: "#d48806" }}>
              🎖️ {text}
            </Typography.Text>
          </div>
        );
      }

      default:
        return null;
    }
  };

  // 过滤掉夜晚行动日志（在右侧时间线面板中展示）
  const visibleLogs = state.logs.filter(
    (l) =>
      l.type !== "game.night_action" &&
      l.type !== "game.wolf_discussion" &&
      l.type !== "game.phase_change" &&
      l.type !== "game.death" &&
      l.type !== "game.control"
  );

  // 收集死亡信息
  const deadPlayers = state.logs
    .filter((l) => l.type === "game.death")
    .map((l) => l.data as { player_id: number; cause: string; round: number });

  return (
    <Layout style={{ minHeight: "100vh", background: "#f5f5f5" }}>
      {/* 顶部栏 */}
      <Layout.Header
        style={{
          background: "#fff",
          padding: "0 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid #f0f0f0",
        }}
      >
        <Space>
          <Button
            icon={<ArrowLeftOutlined />}
            type="text"
            onClick={() => navigate("/game")}
          />
          <Typography.Title level={4} style={{ margin: 0 }}>
            AI 狼人杀
          </Typography.Title>
          <Tag color="blue">
            {PHASE_LABELS[state.phase] || state.phase}
          </Tag>
          {state.round > 0 && (
            <Tag>第{state.round}轮</Tag>
          )}
          {connectionStatus === "reconnecting" && (
            <Tag color="warning">重连中...</Tag>
          )}
          {connectionStatus === "disconnected" && (
            <Tag color="error">已断开</Tag>
          )}
        </Space>

        <Space>
          <Switch
            checkedChildren={<EyeOutlined />}
            unCheckedChildren={<EyeInvisibleOutlined />}
            checked={showThinking}
            onChange={setShowThinking}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            思考过程
          </Typography.Text>

          <Divider orientation="vertical" />

          {state.paused ? (
            <Button
              icon={<PlayCircleOutlined />}
              onClick={resume}
              type="primary"
            >
              继续
            </Button>
          ) : (
            <Button icon={<PauseCircleOutlined />} onClick={pause}>
              暂停
            </Button>
          )}
        </Space>
      </Layout.Header>

      <Layout.Content style={{ padding: 16, display: "flex", flexDirection: "column", height: "calc(100vh - 64px)" }}>
        {/* 玩家面板 */}
        <div style={{ marginBottom: 16, flexShrink: 0 }}>
          <PlayerPanel
            players={state.players}
            thinkingPlayers={state.thinkingPlayers}
            sheriff={state.sheriff}
            deadPlayers={deadPlayers}
            configMap={configMap}
          />
        </div>

        {/* 对话区 + 时间线面板，各占一半 */}
        <div style={{ flex: 1, display: "flex", gap: 16, minHeight: 0 }}>
          {/* 主内容区：白天对话 + 法官叙述 */}
          <div
            ref={logContainerRef}
            style={{
              flex: 1,
              background: "#fff",
              borderRadius: 8,
              padding: 16,
              overflow: "auto",
            }}
          >
            {visibleLogs.length === 0 ? (
              <div style={{ textAlign: "center", padding: 40, color: "#999" }}>
                {state.phase === "GAME_START"
                  ? "等待游戏开始..."
                  : "等待事件..."}
              </div>
            ) : (
              visibleLogs.map(renderLog)
            )}
            <div ref={logEndRef} />
          </div>

          {/* 右侧：时间线面板（始终显示） */}
          <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
            <TimelinePanel
              logs={state.logs}
              players={state.players}
              thinkingPlayers={state.thinkingPlayers}
              currentRound={state.round}
              currentPhase={state.phase}
              sheriff={state.sheriff}
              showThinking={showThinking}
            />
          </div>
        </div>
      </Layout.Content>
    </Layout>
  );
}
