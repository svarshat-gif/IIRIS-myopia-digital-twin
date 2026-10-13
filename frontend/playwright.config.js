import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', timeout: 30000, workers: 1,
  use: { baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {},
    screenshot: 'only-on-failure', trace: 'retain-on-failure' },
})
