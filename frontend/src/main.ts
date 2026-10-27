import "./styles.css";
import { mountPixelLab } from "./pages/PixelLab";
import { mountPlay } from "./pages/Play";

const root = document.getElementById("app")!;
const path = location.pathname;

if (path.startsWith("/lab")) {
  document.title = "PixelLab";
  mountPixelLab(root);
} else if (path.startsWith("/play/")) {
  void mountPlay(root, decodeURIComponent(path.slice("/play/".length).replace(/\/$/, "")));
} else {
  // Главная и бриф — этап 6.
  root.innerHTML = `<main class="placeholder"><h1>Генератор RPG</h1><p>Скоро здесь можно будет описать историю и сыграть в неё.</p><p><a href="/play/demo" style="color:#e0b030">Сыграть в демо-игру «Погасший маяк»</a></p></main>`;
}
