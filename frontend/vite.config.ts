import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: API + share pages come from the local backend (uvicorn on 8080).
// Prod: Firebase Hosting rewrites /api/** and /v/** to Cloud Run (firebase.json).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8080", "/v": "http://127.0.0.1:8080" },
  },
  build: { sourcemap: false, target: "es2022" },
});
