import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5173,
    strictPort: true,
    proxy: {
      "/api": `http://localhost:${process.env.BACKEND_PORT || 8180}`,
      "/clips": `http://localhost:${process.env.BACKEND_PORT || 8180}`,
    },
  },
});
