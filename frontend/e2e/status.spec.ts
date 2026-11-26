import { expect, test, type Page } from '@playwright/test';
import type { SystemStatus } from '../src/shared/api';

const status: SystemStatus = {
  status: 'ok',
  timestamp: 1795530000,
  database: { connected: true, engine: 'PostgreSQL 16', latency_ms: 0.87 },
  queue: { status: 'available', jobs_pending: 2, jobs_doing: 1, jobs_failed: 0, jobs_done: 235 },
  overview: { athletes: 16491, competitions: 340, results: 118890 },
  adapters: [
    {
      id: 1,
      name: 'grom',
      base_url: 'https://grom.example',
      platform: 'grom',
      sport_types: 'run,trail',
      enabled: true,
      competitions_count: 41,
      results_count: 10388,
      open_issues_count: 2,
      status: 'warning',
    },
    {
      id: 2,
      name: 'source-with-a-very-long-unbroken-identifier',
      base_url: null,
      platform: 'platform'.repeat(12),
      sport_types: null,
      enabled: false,
      competitions_count: 0,
      results_count: 0,
      open_issues_count: 0,
      status: 'disabled',
    },
  ],
};

async function checkWidth(page: Page) {
  const widths = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(widths.content).toBeLessThanOrEqual(widths.viewport);
}

async function signInAs(page: Page, role: 'admin' | 'captain' | 'user') {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({ json: { id: 1, username: role, display_name: role, role } }),
  );
}

test.describe('Статус на телефоне', () => {
  test.use({ isMobile: true, hasTouch: true, viewport: { width: 390, height: 844 } });

  test('карточки адаптеров и нижнее меню помещаются в видимую область', async ({ page }) => {
    await signInAs(page, 'admin');
    await page.route('**/api/status', (route) => route.fulfill({ json: status }));
    await page.goto('/');
    await page.getByText('Меню', { exact: true }).click();
    await page.getByRole('link', { name: 'Статус', exact: true }).click();
    const adapters = page.getByRole('region', { name: /Адаптеры источников/ });
    const source = adapters.getByRole('listitem').first();
    await expect(source.getByRole('link', { name: 'Grom' })).toHaveAttribute('href', 'https://grom.example');
    await expect(source.getByText('Бег, Трейл')).toBeVisible();
    await expect(source.getByText('Требует внимания')).toBeVisible();
    await expect(source.locator('dd')).toHaveText(['grom', 'Бег, Трейл', '41', '10 388', '2']);
    await page.evaluate(() => document.fonts.ready);
    const nav = page.getByRole('navigation', { name: 'Разделы', exact: true });
    for (const width of [320, 390, 760]) {
      await page.setViewportSize({ width, height: 844 });
      await checkWidth(page);
      await expect(page.getByRole('button', { name: 'Обновить' })).toBeInViewport({ ratio: 1 });
      for (const link of await nav.getByRole('link').all()) await expect(link).toBeInViewport({ ratio: 1 });
      const bottom = await nav.evaluate((el) => el.getBoundingClientRect().bottom);
      expect(bottom).toBeCloseTo(await page.evaluate(() => window.visualViewport?.height ?? innerHeight), 0);
    }
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const last = await adapters.getByRole('listitem').last().boundingBox();
    const bar = await nav.boundingBox();
    expect(last && bar && last.y + last.height <= bar.y + 1).toBe(true);
    await nav.getByRole('link', { name: 'Найти себя' }).click();
    await expect(page.getByRole('heading', { name: 'Найти себя' })).toBeVisible();
  });

  for (const role of ['guest', 'user', 'captain'] as const) {
    test(`прямая ссылка на статус закрыта для роли ${role}`, async ({ page }) => {
      let requests = 0;
      await page.route('**/api/status', (route) => {
        requests++;
        return route.fulfill({ json: status });
      });
      if (role !== 'guest') await signInAs(page, role);
      await page.goto('/status');
      if (role === 'guest') {
        await expect(page.getByRole('heading', { name: 'Вход в систему' })).toBeVisible();
      } else {
        await expect(page.getByText('Требуются права администратора')).toBeVisible();
        await expect(page.getByRole('navigation', { name: 'Разделы', exact: true })).toBeInViewport();
      }
      await expect(page.getByText('PostgreSQL 16')).toHaveCount(0);
      expect(requests).toBe(0);
    });
  }
});

test('таблица на широком экране, карточки на планшете и обновление данных', async ({ page }) => {
  await signInAs(page, 'admin');
  let data = status;
  await page.route('**/api/status', (route) => route.fulfill({ json: data }));
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.goto('/status');
  const table = page.getByRole('table', { name: /Адаптеры источников/ });
  await expect(table.getByRole('columnheader')).toHaveCount(7);
  await expect(table.getByRole('cell', { name: 'Отключён' })).toBeVisible();
  await checkWidth(page);
  await page.setViewportSize({ width: 820, height: 1180 });
  await expect(table).toBeHidden();
  await expect(page.getByRole('listitem')).toHaveCount(2);
  await checkWidth(page);
  data = { ...status, adapters: [] };
  await page.getByRole('button', { name: 'Обновить' }).click();
  await expect(page.getByText('Источники данных пока не зарегистрированы')).toBeVisible();
});
