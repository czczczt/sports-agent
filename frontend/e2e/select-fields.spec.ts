import { expect, test, type Locator, type Page } from '@playwright/test';

const longSource = 'test-' + 'very-long-source-name-'.repeat(6);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({
      json: { id: 1, username: 'admin', role: 'admin', display_name: 'Администратор' },
    }),
  );
  await page.route('**/api/events?*', (route) => route.fulfill({ json: [] }));
});

async function checkFitsScreen(page: Page, list: Locator) {
  const box = await list.boundingBox();
  const viewport = page.viewportSize();
  if (!box || !viewport) throw new Error('Список должен быть виден');
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
}

test('фильтр площадки поддерживает клавиатуру, применение и сброс', async ({ page }) => {
  await page.goto('/events-view');
  const field = page.getByRole('combobox', { name: 'Площадка' });
  const list = page.getByRole('listbox', { name: 'Площадка' });
  await field.focus();
  await page.keyboard.press('Space');
  await expect(list.getByRole('option', { name: 'Все площадки' })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('End');
  await page.keyboard.press('Escape');
  await expect(field).toBeFocused();
  await expect(field).toHaveText('Все площадки');
  await field.press('ArrowDown');
  await page.keyboard.press('t');
  await page.keyboard.press('Enter');
  await expect(field).toHaveText('Timerman');
  await expect(list).toBeHidden();
  await page.getByRole('button', { name: 'Применить' }).click();
  await expect(page).toHaveURL(/source=timerman/);
  await page.reload();
  await expect(field).toHaveText('Timerman');
  await field.click();
  await page.getByRole('heading', { name: 'Старты', exact: true }).click();
  await expect(list).toBeHidden();
  await page.getByRole('button', { name: 'Сбросить' }).click();
  await expect(field).toHaveText('Все площадки');
});

test('выбор спорта работает внутри диалога на коротком и узком экране', async ({ page }) => {
  await page.setViewportSize({ width: 568, height: 320 });
  await page.goto('/events-view');
  await page.getByRole('button', { name: 'Запланировать старт' }).click();
  const dialog = page.getByRole('dialog');
  const sport = dialog.getByRole('combobox', { name: 'Вид спорта' });
  const list = dialog.getByRole('listbox');
  await sport.click();
  await checkFitsScreen(page, list);
  await page.keyboard.press('Escape');
  await expect(list).toBeHidden();
  await expect(dialog).toBeVisible();
  await page.setViewportSize({ width: 320, height: 568 });
  await sport.click();
  await checkFitsScreen(page, list);
  await list.getByRole('option', { name: 'Лыжи' }).click();
  await expect(sport).toHaveText('Лыжи');
  await dialog.getByLabel('Название старта').fill('Лыжный старт');
  await dialog.getByRole('textbox', { name: 'Дата начала' }).fill('15.12.2026');
  await page.route('**/api/admin/events/planned', (route) => route.fulfill({ json: { id: 2 } }));
  const sent = page.waitForRequest('**/api/admin/events/planned');
  await dialog.getByRole('button', { name: 'Запланировать', exact: true }).click();
  expect((await sent).postDataJSON()).toMatchObject({ sport: 'ski' });
});

test('оба фильтра правок работают с длинным списком из API', async ({ page }) => {
  await page.route('**/api/agent-review/page?*', (route) =>
    route.fulfill({
      json: {
        statuses: ['proposed', 'approved', 'all'],
        sources: [...Array.from({ length: 32 }, (_, i) => `source-${i}`), longSource],
        items: [],
      },
    }),
  );
  await page.route('**/api/agent-review/recipes*', (route) => route.fulfill({ json: [] }));
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto('/agent-review');
  await page.getByRole('combobox', { name: 'Статус' }).click();
  await page.getByRole('option', { name: 'approved' }).click();
  const field = page.getByRole('combobox', { name: 'Площадка' });
  await field.click();
  const list = page.getByRole('listbox');
  await expect(list.getByRole('option')).toHaveCount(34);
  await page.keyboard.press('End');
  await expect(list.getByRole('option', { name: longSource })).toBeInViewport();
  await checkFitsScreen(page, list);
  expect(await list.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.keyboard.press('Tab');
  await expect(list).toBeHidden();
  await expect(page.getByRole('button', { name: 'Показать' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp('status=approved&source=' + longSource));
});
