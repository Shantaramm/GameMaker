import { defineConfig } from "vite";

export default defineConfig({
  // библиотека деталей и демо-игра лежат вне /frontend
  server: {
    fs: { allow: [".."] },
    // API бэкенда: uvicorn app.main:app (порт 8000)
    proxy: { "/api": process.env.API_URL ?? "http://127.0.0.1:8000" },
  },
  // SPA: /lab и /play/* отдаются тем же index.html
  appType: "spa",
});
