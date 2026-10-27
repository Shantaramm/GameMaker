import { defineConfig } from "vite";

export default defineConfig({
  // библиотека деталей и демо-игра лежат вне /frontend
  server: { fs: { allow: [".."] } },
  // SPA: /lab и /play/* отдаются тем же index.html
  appType: "spa",
});
