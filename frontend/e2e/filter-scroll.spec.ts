import { expect, test, type Locator, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({ json: { id: 1, username: 'test', display_name: 'Тест', role: 'user' } }),
  );
});

// Keep the next response pending so a temporary collapse is observable, even on localhost.
async function switchWhileScrolled(page: Page, link: Locator, api: string, json: unknown) {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(api, async (route) => {
    await pending;
    await route.fulfill({ json });
  });
  await page.evaluate(() => document.fonts.ready);
  const before = await link.evaluate((element) => {
    const header = document.querySelector('header')!.getBoundingClientRect();
    window.scrollBy(0, element.getBoundingClientRect().top - header.bottom - 12);
    return window.scrollY;
  });
  expect(before).toBeGreaterThan(30);
  try {
    await Promise.all([page.waitForRequest(api), link.click()]);
    const during = await page.evaluate(
      () =>
        new Promise<number>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve(window.scrollY))),
        ),
    );
    expect(Math.abs(during - before)).toBeLessThanOrEqual(2);
  } finally {
    release();
  }
  return before;
}

for (const width of [390, 1280]) {
  test.describe(`Прокрутка при ширине ${width} px`, () => {
    test.use({ viewport: { width, height: 720 } });

    test('выбор пола сохраняет позицию до и после загрузки рейтинга', async ({ page }) => {
      const rating = (name: string) => ({
        period_start: '2025-11-25',
        period_end: '2026-11-25',
        total: 40,
        rows: Array.from({ length: 40 }, (_, i) => ({
          athlete_id: i + 1,
          display_name: `${name} ${i + 1}`,
          rank: i + 1,
          points: 80,
          starts_count: 1,
        })),
      });
      await page.route('**/api/rating?*', (route) => route.fulfill({ json: rating('Участник') }));
      await page.goto('/rating-view');
      await expect(page.getByRole('link', { name: 'Участник 1', exact: true })).toBeVisible();
      const filter = page.getByRole('link', { name: 'Женщины' });
      const before = await switchWhileScrolled(page, filter, '**/api/rating?*gender=F*', rating('Участница'));
      await expect(page.getByRole('link', { name: 'Участница 1', exact: true })).toBeVisible();
      await expect(filter).toHaveAttribute('aria-current', 'page');
      expect(Math.abs((await page.evaluate(() => window.scrollY)) - before)).toBeLessThanOrEqual(2);
    });

    test('выбор другой дистанции сохраняет позицию при загрузке протокола', async ({ page }) => {
      const races = [
        { id: 11, name_raw: '1500 м' },
        { id: 12, name_raw: '1 миля' },
      ] as const;
      const protocol = (race: (typeof races)[number]) => ({
        race,
        event: { id: 3, title: 'Стадион', date_begin: '2026-11-25', races },
        rating_leaders: [],
        results: Array.from({ length: 40 }, (_, i) => ({
          result_id: i + 1,
          place_abs: i + 1,
          full_name_raw: `Бегун ${i + 1}`,
          status: 'FIN',
        })),
      });
      await page.route('**/api/races/11?*', (route) => route.fulfill({ json: protocol(races[0]) }));
      await page.goto('/races-view/11');
      const pill = page
        .getByRole('navigation', { name: 'Дистанции старта' })
        .getByRole('link', { name: '1 миля' });
      await expect(pill).toBeVisible();
      const before = await switchWhileScrolled(page, pill, '**/api/races/12?*', protocol(races[1]));
      await expect(page.getByRole('heading', { name: '1 миля' })).toBeVisible();
      await expect(pill).toHaveAttribute('aria-current', 'page');
      expect(Math.abs((await page.evaluate(() => window.scrollY)) - before)).toBeLessThanOrEqual(2);
    });
  });
}
