// Обёртка над HTTP API бэкенда (SPEC §10).

import type { PortraitSpec } from "./types/game";

export class ApiError extends Error {}

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Сервер недоступен. Проверьте соединение.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new ApiError(typeof detail === "string" ? detail : res.status === 422 ? "Проверьте текст: он слишком короткий или длинный." : `Ошибка сервера (${res.status}).`);
  }
  return data as T;
}

export interface Brief {
  brief_markdown: string;
  questions: string[];
  provider: string;
}

export interface Preview {
  title: string;
  logline: string;
  characters: { id: string; name: string; role: string; appearance: PortraitSpec }[];
  locations: number;
}

export interface Status {
  status: string;
  step: string;
  progress: number;
  error: string | null;
  provider: string;
  outline: Preview | null;
  detail: { done: number; total: number } | string[] | null;
  queue_position?: number;
}

export const api = {
  info: () => call<{ provider: string; max_brief: number }>("GET", "/api/info"),
  brief: (idea: string) => call<Brief>("POST", "/api/brief", { idea }),
  create: (brief: string) => call<{ game_id: string }>("POST", "/api/games", { brief }),
  status: (id: string) => call<Status>("GET", `/api/games/${encodeURIComponent(id)}/status`),
};

// Черновики между страницами: идея и бриф живут в sessionStorage вкладки.
export const draft = {
  get(key: "idea" | "brief" | "questions"): string {
    try {
      return sessionStorage.getItem(`draft:${key}`) ?? "";
    } catch {
      return "";
    }
  },
  set(key: "idea" | "brief" | "questions", value: string): void {
    try {
      sessionStorage.setItem(`draft:${key}`, value);
    } catch {
      // приватный режим: черновик не переживёт перезагрузку
    }
  },
};
