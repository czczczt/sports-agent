import { expect, test } from '@playwright/test';

const user = { id: 1, username: 'test', role: 'admin', display_name: 'Тест' };
test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    let json: unknown;
    switch (url.pathname) {
      case '/api/auth/me':
        json = user;
        break;
      case '/api/auth/login':
        json = { user, access_token: 'test-session', token_type: 'bearer' };
        break;
      case '/api/auth/register':
        json = { status: 'pending', message: 'Ожидает подтверждения', user_id: 1 };
        break;
      case '/api/auth/logout':
        json = { status: 'ok' };
        break;
      case '/api/athletes/search':
        json = [{ id: 7, display_name: 'Иван Иванов', birth_year: 1990, starts_count: 0, results_count: 0 }];
        break;
      case '/api/athletes/7/summary':
        json = {
          athlete: { id: 7, display_name: 'Иван Иванов' },
          total_starts: 0,
          personal_bests: [],
          dynamics: [],
          rating: { status: 'no_data', message: 'Нет данных' },
        };
        break;
      case '/api/athletes/7/results':
      case '/api/events':
        json = [];
        break;
      case '/api/rating':
        json = { rows: [], total: 0 };
        break;
      case '/api/rating/formula':
        json = { year: 2026, norms: [] };
        break;
      default:
        return route.fulfill({ status: 404, json: { detail: 'Не найдено' } });
    }
    return route.fulfill({ json });
  });
});

test('вход, поиск спортсмена, открытие профиля и выход', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Логин или Email').fill('test');
  await page.getByLabel('Пароль', { exact: true }).fill('secret');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await page.getByLabel('Фамилия').fill('Иванов');
  await page.getByLabel('Год рождения').fill('1990');
  await page.getByRole('button', { name: 'Найти', exact: true }).click();
  await expect(page.getByText('Иван Иванов')).toBeVisible();
  await page.locator('a[href="/athletes-view/7"]').click();
  await expect(page.getByRole('heading', { name: 'Иван Иванов' })).toBeVisible();
  await page.getByRole('button', { name: 'Выйти' }).click();
  await expect(page.getByRole('heading', { name: 'Вход в систему' })).toBeVisible();
});

test('фильтр рейтинга переживает обновление и возврат со страницы формулы', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.goto('/rating-view');
  await page.getByRole('link', { name: 'Женщины' }).click();
  await expect(page).toHaveURL(/gender=F/);
  await page.reload();
  await expect(page.getByRole('link', { name: 'Женщины' })).toHaveClass(/is-active/);
  await page.getByRole('link', { name: 'Как считается беговой рейтинг' }).click();
  await expect(page.getByRole('heading', { name: 'Как посчитано' })).toBeVisible();
  await page.getByRole('button', { name: 'Триатлон', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Триатлон (TriStats)' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Нормативы бега' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Все виды' }).click();
  await expect(page.getByRole('heading', { name: 'Лыжный рейтинг и биатлон' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Трейлраннинг' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Нормативы бега' })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/gender=F/);
});

test('каталог на телефоне сохраняет фильтры и показывает пустой результат', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.goto('/events-view');
  await page.getByLabel('Название забега').fill('Марафон');
  await page.getByRole('button', { name: 'Применить' }).click();
  await expect(page.getByText('Стартов не найдено')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Название забега')).toHaveValue('Марафон');
  await expect(page.getByRole('heading', { name: 'Старты' })).toBeVisible();
});

test('все разделы администратора доступны при смене ширины экрана', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({
      json: { ...user, display_name: 'Пользователь с очень длинным именем и фамилией' },
    }),
  );
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Найти себя' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  for (const width of [320, 390, 760, 761, 955, 1185, 1440, 1920]) {
    await page.setViewportSize({ width, height: 800 });
    const header = page.locator('.app-header');
    if (width <= 760) {
      await page.getByText('Меню', { exact: true }).click();
      await expect(
        page.getByRole('navigation', { name: 'Дополнительные разделы' }).getByRole('link'),
      ).toHaveCount(3);
      await expect(page.locator('.bottom-nav a')).toHaveCount(4);
    }
    for (const name of [
      'Старты',
      'Рейтинг',
      'Найти себя',
      'Заявки',
      'Правки агента',
      'Обновление данных',
      'Статус',
    ]) {
      const link = page.getByRole('link', { name, exact: true });
      await expect(link).toBeInViewport();
      await link.click({ trial: true });
    }
    await expect(header.getByRole('button', { name: 'Выйти' })).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if (width <= 760) await page.keyboard.press('Escape');
  }
  await page.setViewportSize({ width: 320, height: 568 });
  await page.getByText('Меню', { exact: true }).click();
  await page.getByRole('link', { name: 'Заявки', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Модерация заявок' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Дополнительные разделы' })).toBeHidden();
});

test('календарь среза синхронизируется с URL, выбором дня и сбросом', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.goto('/rating-view?as_of=2026-11-10&gender=F');
  const date = page.getByLabel('Срез на дату');
  await expect(date).toHaveValue('10.11.2026');
  await page.getByRole('button', { name: 'Открыть календарь среза' }).click();
  const picker = page.locator('.single-date-calendar.-active-');
  await picker.locator('[data-date="12"][data-month="10"][data-year="2026"]').click();
  await expect(page).toHaveURL(/as_of=2026-11-12/);
  await date.fill('01.12.2026');
  await expect(page).toHaveURL(/as_of=2026-12-01/);
  await page.goBack();
  await expect(date).toHaveValue('12.11.2026');
  await page.getByRole('button', { name: 'Сбросить' }).click();
  await expect(date).toHaveValue('');
  await expect(page).toHaveURL(/\?gender=F$/);
});

test('мобильное меню показывает разделы по роли', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  for (const role of ['captain', 'user']) {
    await page.route('**/api/auth/me', (route) => route.fulfill({ json: { ...user, role } }));
    await page.goto('/');
    await page.getByText('Меню', { exact: true }).click();
    const menu = page.getByRole('navigation', { name: 'Дополнительные разделы' });
    await expect(menu.getByRole('link', { name: 'Статус' })).toHaveCount(0);
    await expect(menu.getByRole('link', { name: 'Заявки' })).toHaveCount(role === 'captain' ? 1 : 0);
    await expect(menu.getByRole('link', { name: 'Правки агента' })).toHaveCount(0);
    await page.unroute('**/api/auth/me');
  }
});

test('форма старта на телефоне принимает даты из календаря и с клавиатуры', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.route('**/api/admin/events/planned', (route) => route.fulfill({ json: { id: 8 } }));
  await page.goto('/events-view');
  await page.getByRole('button', { name: 'Запланировать старт' }).click();
  const dialog = page.getByRole('dialog', { name: 'Запланировать старт' });
  await dialog.getByLabel('Название старта').fill('Осенний марафон');
  await dialog.getByRole('button', { name: 'Открыть календарь даты начала' }).click();
  const picker = dialog.locator('.single-date-calendar.-active-');
  await expect(picker).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(picker).toBeHidden();
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Открыть календарь даты начала' }).click();
  const day = picker.locator('.air-datepicker-cell.-day-:not(.-other-month-)').nth(10);
  const startDate = await day.evaluate((el) => {
    const { year, month, date } = (el as HTMLElement).dataset;
    return [year, String(Number(month) + 1).padStart(2, '0'), date?.padStart(2, '0')].join('-');
  });
  await day.click();
  await dialog.getByRole('textbox', { name: 'Дата окончания' }).fill('31.12.2027');
  const sent = page.waitForRequest('**/api/admin/events/planned');
  await dialog.getByRole('button', { name: 'Запланировать', exact: true }).click();
  expect((await sent).postDataJSON()).toMatchObject({
    title: 'Осенний марафон',
    planned_date_start: startDate,
    planned_date_end: '2027-12-31',
  });
  await expect(dialog).toBeHidden();
});

test('заявка на регистрацию валидирует поля и отправляет данные', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Подать заявку на доступ' }).click();
  await page.getByLabel('Фамилия *').fill('Иванов');
  await page.getByLabel('Имя *', { exact: true }).fill('Иван');
  await page.getByLabel('Логин *').fill('test');
  await page.getByLabel('Email *').fill('ivan@example.test');
  await page.getByLabel('Пароль *').fill('123');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Подать заявку', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('не менее 6');
  await page.getByLabel('Пароль *').fill('example-password');
  const sent = page.waitForRequest((req) => req.url().endsWith('/api/auth/register'));
  await page.getByRole('button', { name: 'Подать заявку', exact: true }).click();
  expect((await sent).postDataJSON()).toMatchObject({
    username: 'test',
    email: 'ivan@example.test',
    consent: true,
    city: null,
  });
  await expect(page.getByRole('status')).toContainText('Заявка принята');
});

test('модератор отклоняет заявку и видит обновлённый список', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  const item = {
    id: 17,
    username: 'ivan',
    status: 'pending',
    role: 'user',
    first_name: 'Иван',
    last_name: 'Иванов',
  };
  let decided = false;
  await page.route('**/api/admin/access-requests?*', (route) =>
    route.fulfill({ json: decided ? [] : [item] }),
  );
  await page.route('**/api/admin/access-requests/17/decision', (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ decision: 'reject', comment: 'Дубликат' });
    decided = true;
    return route.fulfill({ json: { ...item, status: 'rejected' } });
  });
  await page.goto('/admin');
  await page.getByLabel('Комментарий модератора').fill('Дубликат');
  await page.getByRole('button', { name: 'Отклонить', exact: true }).click();
  await expect(page.getByText('Заявок на доступ не найдено')).toBeVisible();
});

test('очередь сотрудников применяет фильтры и обновляется после решения', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  let decided = false;
  await page.route('**/api/admin/verify-queue?*', (route) => {
    const params = new URL(route.request().url()).searchParams;
    const matching = params.get('top_n') === '20' && !params.has('sport');
    return route.fulfill({
      json:
        matching && !decided
          ? [
              {
                athlete_id: 7,
                display_name: 'Иван Иванов',
                sport: 'run',
                gender: 'M',
                rank: 15,
                points: 450,
                starts_count: 2,
              },
            ]
          : [],
    });
  });
  await page.route('**/api/admin/verify-queue/7/decision', (route) => {
    expect(route.request().postDataJSON()).toEqual({ status: 'not_employee', comment: 'Проверено' });
    decided = true;
    return route.fulfill({
      json: {
        success: true,
        athlete_id: 7,
        new_status: 'not_employee',
        auto_blocked_user: true,
        message: 'Решение сохранено',
      },
    });
  });
  await page.goto('/admin/requests?tab=reports');
  await page.getByRole('button', { name: 'Очередь «не проверен»' }).click();
  await page.getByRole('button', { name: '20', exact: true }).click();
  await page.getByRole('button', { name: 'Все', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Иван Иванов' })).toBeVisible();
  await page.reload();
  await page.getByLabel('Примечание проверки в «Пульсе»').fill('Проверено');
  await page.getByRole('button', { name: 'Не сотрудник', exact: true }).click();
  await expect(page.getByText('Очередь проверки пуста')).toBeVisible();
  await expect(page.getByRole('status')).toContainText('связанный пользователь заблокирован');
});
