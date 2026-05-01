import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './playwright',
  use: { baseURL: 'http://127.0.0.1:8765' },
});
