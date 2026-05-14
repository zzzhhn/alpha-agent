// frontend/vitest.config.ts
//
// First frontend test runner (Phase 4b). Node environment, every unit
// test here is for Node-only code (the password wrapper, the Postgres
// rate limiter, the "use server" Server Actions); none of them touch the
// DOM, so jsdom is not needed. The @ alias mirrors tsconfig.json's
// paths so test files can `import ... from "@/lib/auth/password"`.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
