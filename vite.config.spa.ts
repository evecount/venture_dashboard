import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  base: "/venture_dashboard/",
  plugins: [tailwindcss(), react(), tsconfigPaths()],
  build: {
    outDir: "dist",
  },
});
