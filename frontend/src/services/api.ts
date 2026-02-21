import { getToken, logout } from "./auth";

const API_BASE = "/api";

// DTO 类型定义
export interface LLMConfigDTO {
  id: number;
  name: string;
  api_url: string;
  api_key_masked: string;
  model_name: string;
  append_chat_path: boolean;
  created_at: string;
  updated_at: string;
}

export interface LLMConfigCreate {
  name: string;
  api_url: string;
  api_key: string;
  model_name: string;
  append_chat_path: boolean;
}

export interface GameCreateDTO {
  player_configs: number[]; // 12个 LLM 配置 ID
}

export interface GameStateDTO {
  game_id: string;
  status: string;
  current_round: number;
  current_phase: string;
  alive_players: number[];
}

export interface HealthDTO {
  status: string;
  app: string;
}

export interface TestResultDTO {
  success: boolean;
  message: string;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...options?.headers },
  });
  if (res.status === 401) {
    logout();
    window.location.href = "/login";
    throw new Error("登录已过期，请重新登录");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail: string }).detail || res.statusText);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  // LLM 配置
  getLLMConfigs: () => request<LLMConfigDTO[]>("/llm-configs"),
  createLLMConfig: (data: LLMConfigCreate) =>
    request<LLMConfigDTO>("/llm-configs", { method: "POST", body: JSON.stringify(data) }),
  updateLLMConfig: (id: number, data: Partial<LLMConfigCreate>) =>
    request<LLMConfigDTO>(`/llm-configs/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteLLMConfig: (id: number) =>
    request<void>(`/llm-configs/${id}`, { method: "DELETE" }),
  testLLMConfig: (id: number) =>
    request<TestResultDTO>(`/llm-configs/${id}/test`, { method: "POST" }),

  // 游戏
  createGame: (data: GameCreateDTO) =>
    request<{ game_id: string }>("/games", { method: "POST", body: JSON.stringify(data) }),
  startGame: (id: string) =>
    request<{ status: string }>(`/games/${id}/start`, { method: "POST" }),
  getGameState: (id: string) => request<GameStateDTO>(`/games/${id}/state`),

  // 健康检查
  health: () => request<HealthDTO>("/health"),
};
