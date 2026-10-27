import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Testnätet för modulen `skal`. Frontenden hade noll tester före den
// (ANALYS.md §5); SPEC-skal.md §12 gör nätet till en gate, inte en bonus.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    include: ["{lib,components,hooks,app}/**/__tests__/**/*.test.{ts,tsx}"],
  },
});
