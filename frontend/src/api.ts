// Обёртка над HTTP API бэкенда (SPEC §10).

import type { BackgroundSpec, CreatureSpec, GameProfile, PortraitSpec } from "./types/game";

export type Profile = Required<GameProfile>;
export const DEFAULT_PROFILE: Profile = { combat: "tactical", dialogue: "rich" };

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
  published: boolean;
}

export interface GameCard {
  id: string;
  title: string;
  logline: string;
  tone: string;
  est_minutes: number | null;
  locations: number;
  endings: number;
  characters: { id: string; name: string; role: string; appearance: PortraitSpec }[];
  background: BackgroundSpec;
  profile?: GameProfile;
  enemy: { id: string; name: string; appearance: PortraitSpec | CreatureSpec } | null;
  featured?: boolean;
  published_at?: number;
}

export const api = {
  info: () => call<{ provider: string; max_brief: number }>("GET", "/api/info"),
  brief: (idea: string, profile: Profile) => call<Brief>("POST", "/api/brief", { idea, profile }),
  create: (brief: string, profile: Profile) => call<{ game_id: string; owner_token: string }>("POST", "/api/games", { brief, profile }),
  status: (id: string) => call<Status>("GET", `/api/games/${encodeURIComponent(id)}/status`),
  catalog: () => call<{ featured: GameCard[]; community: GameCard[] }>("GET", "/api/catalog"),
  publish: (id: string, owner_token: string, published: boolean) =>
    call<{ published: boolean }>("POST", `/api/games/${encodeURIComponent(id)}/publish`, { owner_token, published }),
};

// Игры, созданные в этом браузере: id и секрет автора, которым игру публикуют в каталоге.
// Секрет живёт только здесь — с другого устройства опубликовать или скрыть игру нельзя.
export interface MyGame { id: string; token: string; created: number }
const MINE_KEY = "rpg:mine";

export const mine = {
  list(): MyGame[] {
    try {
      const v = JSON.parse(localStorage.getItem(MINE_KEY) ?? "[]");
      return Array.isArray(v) ? v : [];
    } catch {
      return [];
    }
  },
  get(id: string): MyGame | undefined {
    return mine.list().find((g) => g.id === id);
  },
  add(id: string, token: string): void {
    try {
      localStorage.setItem(MINE_KEY, JSON.stringify([{ id, token, created: Date.now() }, ...mine.list().filter((g) => g.id !== id)].slice(0, 50)));
    } catch {
      // приватный режим: игра будет доступна по ссылке, но без кнопки публикации
    }
  },
};

// Черновики между страницами: идея и бриф живут в sessionStorage вкладки.
export const draft = {
  profile(): Profile {
    try {
      return { ...DEFAULT_PROFILE, ...JSON.parse(draft.get("profile") || "{}") };
    } catch {
      return DEFAULT_PROFILE;
    }
  },
  get(key: "idea" | "brief" | "questions" | "profile"): string {
    try {
      return sessionStorage.getItem(`draft:${key}`) ?? "";
    } catch {
      return "";
    }
  },
  set(key: "idea" | "brief" | "questions" | "profile", value: string): void {
    try {
      sessionStorage.setItem(`draft:${key}`, value);
    } catch {
      // приватный режим: черновик не переживёт перезагрузку
    }
  },
};
