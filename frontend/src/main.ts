import "./styles.css";
import { mountPixelLab } from "./pages/PixelLab";

const root = document.getElementById("app")!;

if (location.pathname.startsWith("/lab")) {
  document.title = "PixelLab";
  mountPixelLab(root);
} else {
  // Главная, бриф и игра — этапы 2б и 6.
  root.innerHTML = `<main class="placeholder"><h1>Генератор RPG</h1><p>Скоро здесь можно будет описать историю и сыграть в неё.</p></main>`;
}
