import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    pool: "forks", // required for ESM + Node16 module resolution
    include: ["tests/**/*.test.ts"],
    environment: "node",
  },
});
