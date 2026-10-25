import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  // Only the unit tests under src/; the browser tests in e2e/ belong to Playwright.
  test: { environment: "jsdom", globals: false, include: ["src/**/*.test.{ts,tsx}"], exclude: ["e2e/**", "node_modules/**"] },
});
