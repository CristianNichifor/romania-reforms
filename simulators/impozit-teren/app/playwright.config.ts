import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  outputDir: '/tmp/land-tax-ui-results',
  timeout: 90_000,
  expect: { timeout: 30_000 },
  workers: 1,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:5192', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // Headless Firefox in the Linux image cannot create the MapLibre WebGL2 context.
    { name: 'firefox', use: { ...devices['Desktop Firefox'], headless: false } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command: 'npm run preview -- --host 0.0.0.0 --port 5192 --strictPort',
    url: 'http://127.0.0.1:5192',
    reuseExistingServer: false,
  },
});
