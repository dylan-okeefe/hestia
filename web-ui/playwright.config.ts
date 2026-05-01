import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './playwright',
  use: { baseURL: 'http://127.0.0.1:8766' },
  webServer: {
    command: 'npx vite preview --port 8766',
    cwd: '.',
    url: 'http://127.0.0.1:8766',
    reuseExistingServer: !process.env.CI,
  },
});
