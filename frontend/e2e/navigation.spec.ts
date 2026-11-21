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
