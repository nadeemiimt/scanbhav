import { defineConfig, devices } from '@playwright/test'

const apiURL = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8000'
const uiURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: uiURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'if [ -x .venv/bin/uvicorn ]; then exec .venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000; else exec uvicorn api:app --host 127.0.0.1 --port 8000; fi',
      cwd: '..',
      url: `${apiURL}/health`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: uiURL,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
})
