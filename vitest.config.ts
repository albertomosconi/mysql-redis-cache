import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    threads: false,
    testTimeout: 15000,
    coverage: {
      enabled: false,
    },
  },
});