// /play/{id} — игра. demo — встроенная демо-игра; остальные id загружаются с бэкенда (этап 6).

import demo from "../data/demo_game.json";
import { publishToggle } from "../ui/publish";
import { GameController, type GameUI } from "../engine/runtime";
import { clearSave, load, type GameState } from "../engine/state";
import { World } from "../engine/world";
import { hash, rng } from "../pixel/rng";
import type { Game } from "../types/game";
import { BattleScreen } from "../ui/BattleScreen";
import { DialoguePanel } from "../ui/DialoguePanel";
import { el } from "../ui/dom";
import { endingScreen, gameOverScreen, Hud, titleScreen, Toasts } from "../ui/Hud";
import { inventoryView, journalView, Sheet, shopView, setSkillNames } from "../ui/Panels";
import { MapScene } from "../world/scene";
import "../game.css";

async function fetchGame(gameId: string): Promise<Game> {
  if (gameId === "demo") return demo as unknown as Game;
  const res = await fetch(`/api/games/${encodeURIComponent(gameId)}`);
  if (!res.ok) throw new Error(res.status === 404 ? "Игра не найдена." : `Сервер ответил ${res.status}.`);
  return (await res.json()) as Game;
}

export async function mountPlay(root: HTMLElement, gameId: string): Promise<void> {
  root.className = "play";
  let game: Game;
  try {
    game = await fetchGame(gameId);
  } catch (e) {
    root.append(el("div", { className: "screen" }, el("div", { className: "screen-box" }, el("h1", { textContent: "Не удалось открыть игру" }), el("p", { textContent: (e as Error).message }))));
    return;
  }
  document.title = game.meta.title;
  const params = new URLSearchParams(location.search);
  const seed = params.get("seed");
  const random = seed !== null ? rng(hash(seed)) : Math.random;

  const world = new World(game, gameId);
  const mapHost = el("div", { className: "map-host" });
  const toasts = new Toasts();
  const dialogue = new DialoguePanel(world, (m) => toasts.show(m));
  const battle = new BattleScreen(world);
  const sheet = new Sheet();
  const overlay = el("div", { className: "overlay" });
  let controller: GameController;
  let scene: MapScene;

  const openSheet = (title: string, view: () => Node[]) => {
    if (controller.busy || sheet.isOpen) return;
    scene.paused = true;
    sheet.open(title, view(), () => {
      scene.paused = false;
      controller.after();
    });
  };
  setSkillNames(world);
  const hud = new Hud(
    () => openSheet(world.game.hero.name, function view(): Node[] {
      return inventoryView(controller.state, controller.world, () => { sheet.replace(view()); hud.update(controller.state, world); }, (m) => toasts.show(m));
    }),
    () => openSheet("Журнал", () => journalView(controller.questViews())),
  );
  root.append(mapHost, hud.root, dialogue.root, battle.root, sheet.root, toasts.root, overlay);

  const restart = () => {
    clearSave(gameId);
    location.reload();
  };

  const ui: GameUI = {
    dialogue: (runner) => dialogue.open(runner),
    battle: (b) => battle.open(b, controller.location, controller.state),
    shop: (shop) => new Promise<void>((resolve) => {
      const view = (): Node[] => shopView(shop, controller.state, world, () => { sheet.replace(view()); hud.update(controller.state, world); });
      scene.paused = true;
      sheet.open(shop.name, view(), () => {
        scene.paused = false;
        resolve();
      });
    }),
    notify: (m) => toasts.show(m),
    enterLocation: () => {
      scene.enterLocation();
      hud.update(controller.state, world);
    },
    ending: (ending) => overlay.replaceChildren(endingScreen(ending, `${location.origin}/play/${gameId}`, restart, publishToggle(gameId))),
    gameOver: () => overlay.replaceChildren(gameOverScreen(() => location.reload(), restart)),
    refresh: () => hud.update(controller.state, world),
  };

  const begin = (saved: GameState | null) => {
    overlay.replaceChildren();
    controller = new GameController(game, gameId, ui, random, saved);
    scene = new MapScene(mapHost, controller);
    // хук для сквозного теста и отладки
    (window as unknown as { __rpg: unknown }).__rpg = { controller, scene };
    void controller.start();
  };

  const saved = load(gameId);
  if (saved?.ending) clearSave(gameId);
  const usable = saved && !saved.ending ? saved : null;
  overlay.replaceChildren(titleScreen(world, !!usable, () => begin(usable), () => {
    clearSave(gameId);
    begin(null);
  }));
}
