/**
 * 日志按轮次分组工具
 * 将 GameLog[] 按 phase_change 事件切分为 RoundGroup[]
 */

import type { GameLog } from "../services/websocket";

export interface RoundGroup {
  round: number;
  nightLogs: GameLog[];
  dayLogs: GameLog[];
}

/**
 * 将日志按轮次分组。
 *
 * 分组逻辑：
 * - 遇到 phase_change(NIGHT_PHASE) → 开始新一轮的夜晚
 * - 遇到 phase_change(DAY_PHASE) → 当前轮切换到白天
 * - 其他日志归入当前阶段（夜晚或白天）
 * - 游戏开始前的日志归入 round 0
 */
export function groupLogsByRound(logs: GameLog[]): RoundGroup[] {
  if (logs.length === 0) return [];

  const groups: RoundGroup[] = [];
  let currentRound = 0;
  let currentPhase: "night" | "day" = "day"; // 默认白天（游戏开始阶段）
  let currentGroup: RoundGroup = { round: 0, nightLogs: [], dayLogs: [] };

  for (const log of logs) {
    if (log.type === "game.phase_change") {
      const data = log.data as { phase: string; round?: number };

      if (data.phase === "NIGHT_PHASE") {
        // 新一轮夜晚开始
        const newRound = data.round || currentRound + 1;
        if (currentGroup.nightLogs.length > 0 || currentGroup.dayLogs.length > 0) {
          groups.push(currentGroup);
        }
        currentRound = newRound;
        currentPhase = "night";
        currentGroup = { round: currentRound, nightLogs: [], dayLogs: [] };
        currentGroup.nightLogs.push(log);
      } else if (data.phase === "DAY_PHASE") {
        // 切换到白天（同一轮）
        currentPhase = "day";
        currentGroup.dayLogs.push(log);
      } else if (data.phase === "GAME_END") {
        // 游戏结束日志归入当前阶段
        if (currentPhase === "night") {
          currentGroup.nightLogs.push(log);
        } else {
          currentGroup.dayLogs.push(log);
        }
      } else {
        // GAME_START 等
        if (currentPhase === "night") {
          currentGroup.nightLogs.push(log);
        } else {
          currentGroup.dayLogs.push(log);
        }
      }
    } else {
      // 非 phase_change 日志归入当前阶段
      if (currentPhase === "night") {
        currentGroup.nightLogs.push(log);
      } else {
        currentGroup.dayLogs.push(log);
      }
    }
  }

  // 推入最后一组
  if (currentGroup.nightLogs.length > 0 || currentGroup.dayLogs.length > 0) {
    groups.push(currentGroup);
  }

  return groups;
}
