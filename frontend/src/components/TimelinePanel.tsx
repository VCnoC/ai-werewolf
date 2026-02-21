/**
 * TimelinePanel - 频道 Tab + 按轮次折叠的时间线面板
 *
 * 布局：
 *   📋 游戏时间线
 *   [守卫|狼人|女巫|预言家|结算]   ← 顶层 Tab，始终显示
 *   ▼ 第1轮 [当前]                ← 按轮次折叠
 *     当前 Tab 对应频道的内容
 *   ▶ 第2轮
 */

import { useMemo, useEffect, useRef, useState } from "react";
import { Collapse, Tabs, Tag, Typography, Empty } from "antd";
import type { GameLog, NightActionData, PlayerInfo } from "../services/websocket";
import { groupLogsByRound, type RoundGroup } from "../utils/logGrouper";
import {
  CHANNELS,
  getChannelActions,
  renderAction,
  renderAiNotes,
} from "./NightPanel";

interface Props {
  logs: GameLog[];
  players: Record<string, PlayerInfo>;
  thinkingPlayers: number[];
  currentRound: number;
  currentPhase: string;
  sheriff: number | null;
  showThinking?: boolean;
}

/** 从 nightLogs 中提取 NightActionData */
function extractNightActions(nightLogs: GameLog[]): NightActionData[] {
  return nightLogs
    .filter((l) => l.type === "game.night_action" || l.type === "game.wolf_discussion")
    .map((l) => {
      if (l.type === "game.wolf_discussion") {
        const d = l.data as {
          wolf_id: number;
          target: number;
          discussion_round: number;
          speech: string;
          ai_notes?: string;
        };
        return {
          channel: "wolf_discussion",
          player_id: d.wolf_id,
          target: d.target,
          discussion_round: d.discussion_round,
          speech: d.speech,
          ai_notes: d.ai_notes,
        } as NightActionData;
      }
      return l.data as NightActionData;
    });
}

export default function TimelinePanel({
  logs,
  players,
  thinkingPlayers,
  currentRound,
  currentPhase,
  sheriff,
  showThinking = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  // 按轮次分组
  const roundGroups = useMemo(() => groupLogsByRound(logs), [logs]);

  // 每轮的夜晚行动数据
  const roundActions = useMemo(() => {
    const map: Record<number, NightActionData[]> = {};
    for (const group of roundGroups) {
      map[group.round] = extractNightActions(group.nightLogs);
    }
    return map;
  }, [roundGroups]);

  // 受控展开：自动展开最新轮
  const [openKeys, setOpenKeys] = useState<string[]>([]);

  useEffect(() => {
    if (roundGroups.length === 0) return;
    const lastGroup = roundGroups[roundGroups.length - 1];
    const lastKey = String(lastGroup.round);
    setOpenKeys((prev) => {
      if (prev.includes(lastKey)) return prev;
      return [...prev, lastKey];
    });
  }, [roundGroups]);

  // 自动滚动到最新面板
  useEffect(() => {
    if (containerRef.current) {
      const panels = containerRef.current.querySelectorAll(".ant-collapse-item");
      const lastPanel = panels[panels.length - 1];
      if (lastPanel) {
        lastPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [roundGroups.length]);

  // 构建顶层 Tab：每个频道一个 Tab，内部按轮次折叠
  const tabItems = CHANNELS.map((ch) => {
    // 过滤出有该频道数据的轮次（跳过 round 0）
    const relevantRounds = roundGroups.filter(
      (g) => g.round > 0 && getChannelActions(roundActions[g.round] || [], ch.key).length > 0
    );

    // 判断当前是否有玩家在该频道思考中
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

    const collapseItems = relevantRounds.map((group) => {
      const actions = getChannelActions(roundActions[group.round] || [], ch.key);
      const isCurrentRound = group.round === currentRound;

      return {
        key: String(group.round),
        label: (
          <span>
            第{group.round}轮
            {isCurrentRound && (
              <Tag color="processing" style={{ marginLeft: 8, fontSize: 11 }}>
                当前
              </Tag>
            )}
          </span>
        ),
        children: (
          <div style={{ padding: "4px 0" }}>
            {actions.map((a, i) => (
              <div key={i}>
                {renderAction(a, i, players)}
                {renderAiNotes(a, showThinking)}
              </div>
            ))}
          </div>
        ),
      };
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
        collapseItems.length > 0 ? (
          <Collapse
            activeKey={openKeys}
            onChange={(keys) => setOpenKeys(keys as string[])}
            items={collapseItems}
            size="small"
            style={{ background: "transparent" }}
          />
        ) : (
          <Empty
            description={isThinking ? "思考中..." : "暂无数据"}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ),
    };
  });

  return (
    <div
      ref={containerRef}
      style={{
        height: "100%",
        overflow: "auto",
        background: "#fff",
        borderRadius: 8,
        padding: 8,
      }}
    >
      <Typography.Title level={5} style={{ margin: "0 0 8px 8px" }}>
        📋 游戏时间线
      </Typography.Title>
      <Tabs
        items={tabItems}
        size="small"
        tabBarStyle={{ marginBottom: 8 }}
      />
    </div>
  );
}
