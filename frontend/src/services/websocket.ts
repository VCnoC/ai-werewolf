import { useCallback, useEffect, useRef, useState } from "react";

// ========== 游戏事件类型定义 ==========

export interface PhaseChangeData {
  phase: string;
  round: number;
}

export interface NightActionData {
  channel: string;
  player_id?: number;
  player_ids?: number[];
  action?: string;
  target?: number | null;
  result?: string;
  victim?: number | null;
  save?: boolean;
  poison_target?: number | null;
  detail?: string;
  wolf_target?: number | null;
  ai_notes?: string | Record<number, string>;
  _parse_level?: number;
  [key: string]: unknown;  // 允许结算事件的额外字段
}

export interface SpeechData {
  player_id: number;
  content: string;
  is_last_words?: boolean;
  is_explode?: boolean;
  ai_notes?: string;
  _parse_level?: number;
}

export interface VoteData {
  votes: Record<number, number>;
  counts: Record<number, number>;
}

export interface DeathData {
  player_id: number;
  cause: string;
  shooter?: number;
}

export interface JudgeNarrationData {
  text: string;
  deaths?: number[];
}

export interface AIThinkingData {
  player_id?: number;
  player_ids?: number[];
  phase: string;
}

export interface GameEndData {
  winner: string;
  round: number;
}

export interface GameControlData {
  action: string;
}

export interface GameErrorData {
  message: string;
}

export interface WolfDiscussionData {
  discussion_round: number;
  wolf_id: number;
  target: number;
  speech: string;
  ai_notes?: string;
}

export interface VoteCastData {
  voter_id: number;
  target: number | null;
}

export type GameEvent =
  | { type: "game.phase_change"; data: PhaseChangeData }
  | { type: "game.night_action"; data: NightActionData }
  | { type: "game.wolf_discussion"; data: WolfDiscussionData }
  | { type: "game.speech"; data: SpeechData }
  | { type: "game.vote"; data: VoteData }
  | { type: "game.vote_cast"; data: VoteCastData }
  | { type: "game.death"; data: DeathData }
  | { type: "game.judge_narration"; data: JudgeNarrationData }
  | { type: "game.ai_thinking"; data: AIThinkingData }
  | { type: "game.end"; data: GameEndData }
  | { type: "game.control"; data: GameControlData }
  | { type: "game.error"; data: GameErrorData }
  | { type: "game.sheriff_election"; data: unknown };

// ========== WebSocket 连接管理 ==========

type EventHandler = (event: GameEvent) => void;

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "reconnecting";

type StatusHandler = (status: ConnectionStatus) => void;

export class GameWebSocket {
  private ws: WebSocket | null = null;
  private handlers: EventHandler[] = [];
  private statusHandlers: StatusHandler[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manualClose = false;
  private gameId: string;

  constructor(gameId: string) {
    this.gameId = gameId;
  }

  connect() {
    this.manualClose = false;
    this._notifyStatus("connecting");
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(
      `${protocol}//${location.host}/api/ws/${this.gameId}`
    );

    this.ws.onopen = () => {
      this._notifyStatus("connected");
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as GameEvent;
        this.handlers.forEach((h) => h(msg));
      } catch {
        // 忽略解析失败
      }
    };

    this.ws.onclose = () => {
      if (!this.manualClose) {
        this._notifyStatus("reconnecting");
        this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      } else {
        this._notifyStatus("disconnected");
      }
    };

    this.ws.onerror = () => {
      // onclose 会自动触发重连
    };
  }

  onEvent(handler: EventHandler) {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  onStatus(handler: StatusHandler) {
    this.statusHandlers.push(handler);
    return () => {
      this.statusHandlers = this.statusHandlers.filter((h) => h !== handler);
    };
  }

  private _notifyStatus(status: ConnectionStatus) {
    this.statusHandlers.forEach((h) => h(status));
  }

  send(type: string, data?: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    }
  }

  pause() {
    this.send("game.pause");
  }

  resume() {
    this.send("game.resume");
  }

  disconnect() {
    this.manualClose = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
    this.handlers = [];
    this.statusHandlers = [];
  }
}

// ========== React Hook ==========

export interface GameLog {
  id: number;
  type: string;
  data: unknown;
  timestamp: number;
}

export interface PlayerInfo {
  role: string;
  faction: string;
  is_alive: boolean;
  is_sheriff: boolean;
  llm_config_id?: number;
}

export interface GameUIState {
  phase: string;
  round: number;
  winner: string | null;
  paused: boolean;
  thinkingPlayers: number[];
  logs: GameLog[];
  nightActions: NightActionData[];
  players: Record<string, PlayerInfo>;
  sheriff: number | null;
}

export function useGameWebSocket(gameId: string | undefined) {
  const wsRef = useRef<GameWebSocket | null>(null);
  const logIdRef = useRef(0);
  const thinkingTimersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected");

  const [state, setState] = useState<GameUIState>({
    phase: "GAME_START",
    round: 0,
    winner: null,
    paused: false,
    thinkingPlayers: [],
    logs: [],
    nightActions: [],
    players: {},
    sheriff: null,
  });

  const addLog = useCallback((type: string, data: unknown) => {
    setState((prev) => ({
      ...prev,
      logs: [
        ...prev.logs,
        { id: ++logIdRef.current, type, data, timestamp: Date.now() },
      ],
    }));
  }, []);

  useEffect(() => {
    if (!gameId) return;

    // 先获取初始状态
    fetch(`/api/games/${gameId}/state`)
      .then((r) => r.json())
      .then((data) => {
        setState((prev) => ({
          ...prev,
          phase: data.current_phase,
          round: data.current_round,
          winner: data.winner,
          players: data.players || {},
          sheriff: data.sheriff,
        }));
      })
      .catch(() => {});

    const ws = new GameWebSocket(gameId);
    wsRef.current = ws;

    ws.onEvent((event) => {
      addLog(event.type, event.data);

      switch (event.type) {
        case "game.phase_change":
          setState((prev) => ({
            ...prev,
            phase: event.data.phase,
            round: event.data.round || prev.round,
            nightActions:
              event.data.phase === "NIGHT_PHASE" ? [] : prev.nightActions,
            thinkingPlayers: [],
          }));
          break;

        case "game.night_action": {
          const naPlayerId = event.data.player_id;
          if (naPlayerId != null) {
            const naTimer = thinkingTimersRef.current.get(naPlayerId);
            if (naTimer) {
              clearTimeout(naTimer);
              thinkingTimersRef.current.delete(naPlayerId);
            }
          }
          setState((prev) => ({
            ...prev,
            nightActions: [...prev.nightActions, event.data],
            thinkingPlayers: prev.thinkingPlayers.filter(
              (id) => id !== event.data.player_id
            ),
          }));
          break;
        }

        case "game.wolf_discussion": {
          const wolfId = event.data.wolf_id;
          const wolfTimer = thinkingTimersRef.current.get(wolfId);
          if (wolfTimer) {
            clearTimeout(wolfTimer);
            thinkingTimersRef.current.delete(wolfId);
          }
          setState((prev) => ({
            ...prev,
            nightActions: [
              ...prev.nightActions,
              {
                channel: "wolf_discussion",
                player_id: event.data.wolf_id,
                target: event.data.target,
                discussion_round: event.data.discussion_round,
                speech: event.data.speech,
                ai_notes: event.data.ai_notes,
              } as NightActionData,
            ],
            // 清除该狼人的 thinking 状态
            thinkingPlayers: prev.thinkingPlayers.filter(
              (id) => id !== wolfId
            ),
          }));
          break;
        }

        case "game.ai_thinking":
          setState((prev) => {
            const ids = event.data.player_ids
              ? event.data.player_ids
              : event.data.player_id
                ? [event.data.player_id]
                : [];
            const phase = event.data.phase;

            // 逐个轮流的阶段（投票、发言等）：新玩家思考时替换旧的，而非累加
            const sequentialPhases = ["vote", "discussion", "last_words",
              "sheriff_register", "sheriff_speech", "sheriff_vote",
              "sheriff_adjust_order", "hunter_shoot"];
            const isSequential = sequentialPhases.includes(phase);

            // 超时兜底：30秒后自动清除 thinking 状态
            for (const id of ids) {
              const existing = thinkingTimersRef.current.get(id);
              if (existing) clearTimeout(existing);
              thinkingTimersRef.current.set(
                id,
                setTimeout(() => {
                  setState((p) => ({
                    ...p,
                    thinkingPlayers: p.thinkingPlayers.filter((pid) => pid !== id),
                  }));
                  thinkingTimersRef.current.delete(id);
                }, 30000)
              );
            }

            // 顺序阶段：只保留当前思考的玩家；并行阶段（如狼人商量）：累加
            const newThinking = isSequential
              ? ids
              : [...new Set([...prev.thinkingPlayers, ...ids])];

            return {
              ...prev,
              thinkingPlayers: newThinking,
            };
          });
          break;

        case "game.speech": {
          const speechPid = event.data.player_id;
          const speechTimer = thinkingTimersRef.current.get(speechPid);
          if (speechTimer) {
            clearTimeout(speechTimer);
            thinkingTimersRef.current.delete(speechPid);
          }
          setState((prev) => ({
            ...prev,
            thinkingPlayers: prev.thinkingPlayers.filter(
              (id) => id !== speechPid
            ),
          }));
          break;
        }

        case "game.vote_cast": {
          const voterId = event.data.voter_id;
          // 清除 thinking timer
          const voteTimer = thinkingTimersRef.current.get(voterId);
          if (voteTimer) {
            clearTimeout(voteTimer);
            thinkingTimersRef.current.delete(voterId);
          }
          setState((prev) => ({
            ...prev,
            thinkingPlayers: prev.thinkingPlayers.filter(
              (id) => id !== voterId
            ),
          }));
          break;
        }

        case "game.death":
          setState((prev) => {
            const pid = String(event.data.player_id);
            const p = prev.players[pid];
            if (!p) return prev;
            return {
              ...prev,
              players: {
                ...prev.players,
                [pid]: { ...p, is_alive: false },
              },
              // 清除死亡玩家的 thinking 状态（猎人开枪后等）
              thinkingPlayers: prev.thinkingPlayers.filter(
                (id) => id !== event.data.player_id
              ),
            };
          });
          break;

        case "game.end":
          setState((prev) => ({
            ...prev,
            winner: event.data.winner,
            phase: "GAME_END",
          }));
          break;

        case "game.control":
          setState((prev) => ({
            ...prev,
            paused: event.data.action === "paused",
          }));
          break;

        case "game.sheriff_election": {
          const d = event.data as Record<string, unknown>;
          // 清除 thinking 状态：报名决定和投票
          if (d.phase === "register_decision" && typeof d.player_id === "number") {
            setState((prev) => ({
              ...prev,
              thinkingPlayers: prev.thinkingPlayers.filter(
                (id) => id !== (d.player_id as number)
              ),
            }));
          }
          if (d.phase === "vote_cast" && typeof d.voter_id === "number") {
            setState((prev) => ({
              ...prev,
              thinkingPlayers: prev.thinkingPlayers.filter(
                (id) => id !== (d.voter_id as number)
              ),
            }));
          }
          if (d.phase === "elected" && typeof d.sheriff_id === "number") {
            setState((prev) => {
              const sid = String(d.sheriff_id);
              const updatedPlayers = { ...prev.players };
              // 清除旧警长标记
              for (const [pid, p] of Object.entries(updatedPlayers)) {
                if (p.is_sheriff) {
                  updatedPlayers[pid] = { ...p, is_sheriff: false };
                }
              }
              // 设置新警长
              if (updatedPlayers[sid]) {
                updatedPlayers[sid] = { ...updatedPlayers[sid], is_sheriff: true };
              }
              return {
                ...prev,
                sheriff: d.sheriff_id as number,
                players: updatedPlayers,
              };
            });
          }
          // 警徽流转：转让（后端字段为 "to"）
          if (d.phase === "badge_transferred" && typeof d.to === "number") {
            setState((prev) => {
              const sid = String(d.to);
              const updatedPlayers = { ...prev.players };
              for (const [pid, p] of Object.entries(updatedPlayers)) {
                if (p.is_sheriff) {
                  updatedPlayers[pid] = { ...p, is_sheriff: false };
                }
              }
              if (updatedPlayers[sid]) {
                updatedPlayers[sid] = { ...updatedPlayers[sid], is_sheriff: true };
              }
              return {
                ...prev,
                sheriff: d.to as number,
                players: updatedPlayers,
              };
            });
          }
          // 警徽流转：销毁
          if (d.phase === "badge_destroyed") {
            setState((prev) => {
              const updatedPlayers = { ...prev.players };
              for (const [pid, p] of Object.entries(updatedPlayers)) {
                if (p.is_sheriff) {
                  updatedPlayers[pid] = { ...p, is_sheriff: false };
                }
              }
              return { ...prev, sheriff: null, players: updatedPlayers };
            });
          }
          break;
        }
      }
    });

    ws.onStatus(setConnectionStatus);
    ws.connect();

    return () => {
      ws.disconnect();
      wsRef.current = null;
      // 清除所有 thinking 超时定时器
      for (const timer of thinkingTimersRef.current.values()) {
        clearTimeout(timer);
      }
      thinkingTimersRef.current.clear();
    };
  }, [gameId, addLog]);

  const pause = useCallback(() => wsRef.current?.pause(), []);
  const resume = useCallback(() => wsRef.current?.resume(), []);

  return { state, pause, resume, connectionStatus };
}
