import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests', fullyParallel: true, timeout: 30000,
  testMatch: '**/*.spec.ts',
  use: { headless: true, baseURL: 'http://127.0.0.1:8025', trace: 'retain-on-failure' },
  // No webServer: all HTTP requests are fulfilled from dist or mocked fixtures.
  projects: [{name: 'chromium', use: {browserName: 'chromium'}}],
});
