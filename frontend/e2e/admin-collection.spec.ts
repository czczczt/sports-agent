import { expect, test } from '@playwright/test';

const user = { id: 1, username: 'test', role: 'admin', display_name: 'Тест' };
const baseUrl = '**/api/admin/collection';
const createdAt = '2026-11-25T10:00:00Z';
const sources = [
  { code: 'russiarunning', label: 'RussiaRunning', automatic: true, enabled: true },
  { code: 'resultszone', label: 'Results.Zone', automatic: false, enabled: true },
  { code: 'grom', label: 'Grom', automatic: false, enabled: true },
];

const eventInfo = {
  title: 'Осенний марафон',
  date: '2026-11-21',
  city: 'Екатеринбург',
  is_new: true,
};

const raceInfo = {
  label: 'Десять километров',
  distance_m: 10000,
  sport: 'run',
  relay: false,
};

function protocol(draftId: number | null, source: string, count: number, published = false) {
  return {
    key: `protocol-${draftId ?? 'published'}`,
    draft_id: draftId,
    source,
    title: eventInfo.title,
    date: eventInfo.date,
    city: eventInfo.city,
    url: `https://example.test/${source}`,
    race_name: raceInfo.label,
    distance_m: raceInfo.distance_m,
    sport: raceInfo.sport,
    relay: raceInfo.relay,
    participants: count,
    is_final: source === 'russiarunning',
    published,
    planned: false,
  };
}

const confirmedRace = {
  ...raceInfo,
  key: 'confirmed',
  participants: 300,
  warning: null,
  preferred_protocol_key: 'protocol-1',
  protocols: [protocol(1, 'russiarunning', 300), protocol(2, 'resultszone', 298)],
};

const disputedRace = {
  ...raceInfo,
  key: 'disputed',
  label: 'Пять километров',
  distance_m: 5000,
  participants: 120,
  warning: 'Возможный дубль: число совпавших результатов ниже порога.',
  preferred_protocol_key: null,
  protocols: [
    { ...protocol(1, 'russiarunning', 120), race_name: 'Пять километров', distance_m: 5000 },
    { ...protocol(null, 'grom', 80, true), race_name: 'Пять километров', distance_m: 5000 },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auth_token', 'test-session'));
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: user }));
});

test('запускает сбор, восстанавливает предпросмотр и утверждает дистанции с учётом решения по дублю', async ({
  page,
}) => {
  await page.route(`${baseUrl}/sources`, (route) => route.fulfill({ json: sources }));

  let started = false;
  await page.route(`${baseUrl}/batches`, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: started ? [{ id: 9, created_at: createdAt }] : [] });
    }
    expect(route.request().postDataJSON()).toEqual({
      sources: ['russiarunning', 'resultszone'],
      starts: [{ source: 'resultszone', event_code: 'fall-2026' }],
    });
    started = true;
    return route.fulfill({ status: 202, json: { id: 9 } });
  });

  let reads = 0;
  let approvals = 0;
  await page.route(`${baseUrl}/batches/9`, (route) => {
    const status = reads++ === 0 ? 'running' : 'completed';
    const races = approvals === 0 ? [confirmedRace, disputedRace] : approvals === 1 ? [disputedRace] : [];
    return route.fulfill({
      json: {
        id: 9,
        created_at: createdAt,
        preview_revision: `revision-${approvals}`,
        publication_status: approvals ? 'published' : 'pending',
        publication_error: null,
        sources: [
          { code: 'russiarunning', status, error: null },
          { code: 'resultszone', status, error: null },
        ],
        drafts:
          status === 'running'
            ? []
            : [
                {
                  id: 1,
                  source: 'russiarunning',
                  event_code: 'fall-rr',
                  status: approvals === 2 ? 'approved' : 'ready',
                  error: null,
                },
                {
                  id: 2,
                  source: 'resultszone',
                  event_code: 'fall-2026',
                  status: approvals > 0 ? 'approved' : 'ready',
                  error: null,
                },
              ],
        events:
          status === 'running' || races.length === 0
            ? []
            : [
                {
                  ...eventInfo,
                  key: 'autumn-marathon',
                  source: 'russiarunning',
                  participants: approvals ? 120 : 300,
                  draft_ids: approvals ? [1] : [1, 2],
                  races,
                },
              ],
      },
    });
  });
  const requests: unknown[] = [];
  await page.route(`${baseUrl}/batches/9/approve`, (route) => {
    requests.push(route.request().postDataJSON());
    approvals += 1;
    return route.fulfill({
      json: {
        approved_draft_ids: approvals === 1 ? [2] : [1],
        pending_draft_ids: approvals === 1 ? [1] : [],
        published_races: 1,
        rating_version_id: approvals,
        publication_status: 'published',
      },
    });
  });

  await page.goto('/events-view');
  await page.getByRole('link', { name: 'Обновление данных' }).click();
  await expect(page.getByRole('checkbox', { name: 'RussiaRunning' })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'Results.Zone' })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'Grom' })).toBeChecked();
  await expect(page.getByText('Нужен код старта', { exact: true })).toHaveCount(2);
  await page.getByRole('checkbox', { name: 'Grom' }).uncheck();
  await page.getByText('Указать известные коды стартов').click();
  await page.getByLabel('Коды стартов · Results.Zone').fill('fall-2026, fall-2026');
  await expect(page.getByText('Сбор по коду старта', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Обновить данные', exact: true }).click();
  await expect(page).toHaveURL(/batch=9/);
  await expect(page.getByText('В работе', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('checkbox', { name: eventInfo.title })).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Запуск', exact: true })).toHaveValue('9');
  await expect(page.getByRole('checkbox', { name: 'Grom' })).toBeChecked();

  const preview = page.getByRole('region', { name: 'Предпросмотр и публикация' });
  await expect(preview.getByText('21.11.2026 · Екатеринбург · RussiaRunning · 300 участников')).toBeVisible();
  await preview.getByText('Исходные протоколы').click();
  await expect(preview.getByRole('link', { name: 'Протокол на Results.Zone' })).toBeVisible();
  await expect(preview.getByText('298 участников', { exact: false })).toBeVisible();
  await preview.getByText('Возможный дубль · Есть опубликованный протокол', { exact: true }).click();
  await expect(preview.getByText('число совпавших результатов ниже порога.', { exact: false })).toBeVisible();
  await expect(preview.getByText('Уже опубликован', { exact: true })).toBeVisible();
  await preview.getByRole('radio', { name: 'Отложить решение' }).check();
  await preview.getByRole('checkbox', { name: eventInfo.title }).check();
  await preview.getByRole('button', { name: 'Утвердить выбранное' }).click();
  await expect(preview.getByText('Черновики, ожидающие решения: 1.', { exact: false })).toBeVisible();
  await expect(preview.getByText('Исходные протоколы')).toHaveCount(0);
  await expect(preview.getByRole('checkbox', { name: eventInfo.title })).toBeDisabled();

  await preview.getByRole('radio', { name: /Выбрать RussiaRunning/ }).check();
  await preview.getByRole('checkbox', { name: eventInfo.title }).check();
  await preview.getByRole('button', { name: 'Утвердить выбранное' }).click();
  await expect(preview.getByText('Опубликовано', { exact: true })).toBeVisible();
  await expect(preview.getByText('Нет черновиков для утверждения.')).toBeVisible();
  expect(requests).toEqual([
    { draft_ids: [1, 2], resolutions: [], preview_revision: 'revision-0' },
    {
      draft_ids: [1],
      resolutions: [{ race_key: 'disputed', protocol_key: 'protocol-1' }],
      preview_revision: 'revision-1',
    },
  ]);
});

test('капитан видит отказ в доступе, запросы к сбору не отправляются', async ({ page }) => {
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: { ...user, role: 'captain' } }));
  let accessedCollectionApi = false;
  await page.route(`${baseUrl}/**`, (route) => {
    accessedCollectionApi = true;
    return route.fulfill({ status: 403 });
  });
  await page.goto('/admin/collection');
  await expect(page.getByText('Требуются права администратора', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Обновление данных' })).toHaveCount(0);
  expect(accessedCollectionApi).toBe(false);
});

test('известные ограничения RussiaRunning не отображаются как ошибка источника', async ({ page }) => {
  await page.route(`${baseUrl}/sources`, (route) => route.fulfill({ json: sources }));
  await page.route(`${baseUrl}/batches`, (route) =>
    route.fulfill({ json: [{ id: 9, created_at: createdAt }] }),
  );
  await page.route(`${baseUrl}/batches/9`, (route) =>
    route.fulfill({
      json: {
        id: 9,
        created_at: createdAt,
        preview_revision: 'revision-0',
        publication_status: 'pending',
        publication_error: null,
        sources: [
          {
            code: 'russiarunning',
            status: 'failed',
            error: 'legacy: No final source protocols',
          },
        ],
        drafts: [
          {
            id: 1,
            source: 'russiarunning',
            event_code: 'legacy',
            title: 'Старый запуск',
            status: 'failed',
            error: 'No final source protocols',
          },
          {
            id: 2,
            source: 'russiarunning',
            event_code: 'preliminary',
            title: 'Предварительный протокол',
            status: 'failed',
            error: 'RussiaRunning protocols are not marked final',
          },
        ],
        events: [],
      },
    }),
  );

  await page.goto('/admin/collection?batch=9');

  const progress = page.getByRole('region', { name: 'Ход сбора' });
  await expect(progress.getByText('Ошибка', { exact: true })).toHaveCount(0);
  await expect(progress.getByText('1 без доступного итогового протокола')).toBeVisible();
  await expect(progress.getByText('1 с предварительным протоколом')).toBeVisible();
  await progress.getByText('Старты (2)').click();
  await expect(progress.getByText('Нет доступного итогового протокола', { exact: true })).toBeVisible();
  await expect(
    progress.getByText(
      'RussiaRunning не пометил протокол как итоговый. Старт можно проверить повторно позже.',
    ),
  ).toBeVisible();
  await expect(progress.getByText('No final source protocols')).toHaveCount(0);
});
