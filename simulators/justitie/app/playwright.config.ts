import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser', outputDir: '/tmp/justitie-browser-baselines',
  workers: 1, timeout: 90_000, expect: { timeout: 20_000 }, retries: 0,
  forbidOnly: Boolean(process.env.CI),
  use: { baseURL: 'http://127.0.0.1:5196', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: devices['Desktop Chrome'] },
    { name: 'firefox', use: { ...devices['Desktop Firefox'], headless: false } },
    { name: 'webkit', use: devices['Desktop Safari'] },
  ],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 5196 --strictPort',
    url: 'http://127.0.0.1:5196', reuseExistingServer: false,
  },
});
