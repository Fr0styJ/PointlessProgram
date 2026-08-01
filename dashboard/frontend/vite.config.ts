import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FakeCo Control Dashboard — Phase 33
// Build output goes to ../static so the FastAPI BFF (dashboard/main.py) can
// serve it via a single StaticFiles-equivalent mount with no separate build
// step needed inside the runtime image (the Dockerfile's Node build stage
// runs this, then the runtime stage COPYs ../static in).
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
