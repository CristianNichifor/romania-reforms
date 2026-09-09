import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', outputDir: '/tmp/transport-native-ui', workers: 1,
  timeout: 90_000, expect: { timeout: 30_000 }, retries: 0,
  use: { baseURL: 'http://127.0.0.1:5193', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: devices['Desktop Chrome'] },
    { name: 'firefox', use: { ...devices['Desktop Firefox'], headless: false } },
    { name: 'webkit', use: devices['Desktop Safari'] },
  ],
  webServer: { command: 'npm run preview -- --host 0.0.0.0 --port 5193 --strictPort', url: 'http://127.0.0.1:5193' },
});
