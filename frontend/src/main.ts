import "./styles.css";
import { mountPixelLab } from "./pages/PixelLab";
import { mountPlay } from "./pages/Play";
import { mountBrief, mountHome, mountProgress } from "./pages/Site";

const root = document.getElementById("app")!;

function route(): void {
  const path = location.pathname.replace(/\/$/, "") || "/";
  if (path.startsWith("/lab")) {
    document.title = "PixelLab";
    mountPixelLab(root);
  } else if (path.startsWith("/play/")) {
    void mountPlay(root, decodeURIComponent(path.slice("/play/".length)));
  } else if (path.startsWith("/progress/")) {
    mountProgress(root, decodeURIComponent(path.slice("/progress/".length)));
  } else if (path === "/brief") {
    mountBrief(root);
  } else {
    void mountHome(root);
  }
}

window.addEventListener("popstate", route);
route();
