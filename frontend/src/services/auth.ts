/**
 * 认证服务：Token 管理 + 用户信息存储 + 登录注册 API
 */

const TOKEN_KEY = "werewolf_token";
const USER_KEY = "werewolf_user";

export interface UserInfo {
  id: number;
  username: string;
  created_at: string;
}

export interface LoginResponse {
  token: string;
  user: UserInfo;
}

// ========== Token 管理 ==========

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ========== 用户信息管理 ==========

export function getUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserInfo;
  } catch {
    return null;
  }
}

export function setUser(user: UserInfo): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function removeUser(): void {
  localStorage.removeItem(USER_KEY);
}

// ========== 认证状态 ==========

export function isAuthenticated(): boolean {
  return !!getToken();
}

export function logout(): void {
  removeToken();
  removeUser();
}

// ========== API 调用 ==========

const API_BASE = "/api/auth";

async function authRequest<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail: string }).detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function login(
  username: string,
  password: string
): Promise<LoginResponse> {
  const data = await authRequest<LoginResponse>("/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setToken(data.token);
  setUser(data.user);
  return data;
}

export async function register(
  username: string,
  password: string
): Promise<UserInfo> {
  return authRequest<UserInfo>("/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function getProfile(): Promise<UserInfo> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/profile`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) {
    throw new Error("获取用户信息失败");
  }
  return res.json() as Promise<UserInfo>;
}
