import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import type { CollectionBatch, CollectionStartRequest } from './api';
import { CollectionProgress } from './CollectionProgress';

function batch(): CollectionBatch {
  return {
    id: 9,
    created_at: '2026-11-25T10:00:00Z',
    sources: [
      {
        code: 'russiarunning',
        status: 'failed',
        error: 'unsupported: RussiaRunning has no supported individual distances',
      },
    ],
    drafts: [
      {
        id: 1,
        source: 'russiarunning',
        event_code: 'unsupported',
        title: 'Без личных дистанций',
        status: 'failed',
        error: 'RussiaRunning has no supported individual distances',
      },
      {
        id: 2,
        source: 'russiarunning',
        event_code: 'preliminary',
        title: 'Предварительный',
        status: 'failed',
        error: 'RussiaRunning protocols are not marked final',
      },
      {
        id: 3,
        source: 'russiarunning',
        event_code: 'historical',
        title: 'Исторический',
        status: 'failed',
        error: 'No final source protocols',
      },
    ],
    events: [],
    preview_revision: 'revision',
    publication_status: 'pending',
    publication_error: null,
  };
}

it('объясняет известные причины без красной ошибки и повторяет только проверяемые старты', async () => {
  const onStart = vi.fn<(body: CollectionStartRequest) => void>();
  render(
    <CollectionProgress
      batch={batch()}
      sourceLabel={() => 'RussiaRunning'}
      starting={false}
      onStart={onStart}
    />,
  );

  expect(screen.queryByText('Ошибка')).toBeNull();
  expect(screen.getByText(/1 без поддерживаемых дистанций/i)).toBeTruthy();
  await userEvent.click(screen.getByText('Старты (3)'));
  expect(screen.getByText('Нет поддерживаемых дистанций')).toBeTruthy();
  expect(screen.getByText('Нет доступного итогового протокола')).toBeTruthy();
  expect(screen.queryByText('No final source protocols')).toBeNull();
  expect(screen.queryByText(/unsupported: RussiaRunning/)).toBeNull();

  await userEvent.click(screen.getByRole('button', { name: 'Проверить старты повторно' }));
  expect(onStart).toHaveBeenCalledWith({
    sources: ['russiarunning'],
    starts: [
      { source: 'russiarunning', event_code: 'preliminary' },
      { source: 'russiarunning', event_code: 'historical' },
    ],
  });
});

it('сохраняет отдельную техническую ошибку источника', () => {
  const value = batch();
  const source = value.sources[0];
  if (!source) throw new Error('Тестовый источник не создан');
  source.error = 'HTTP 503';

  render(
    <CollectionProgress
      batch={value}
      sourceLabel={() => 'RussiaRunning'}
      starting={false}
      onStart={() => undefined}
    />,
  );

  expect(screen.getByText('Ошибка')).toBeTruthy();
  expect(screen.getByText('HTTP 503')).toBeTruthy();
  expect(screen.getByText('1 без доступного итогового протокола')).toBeTruthy();
});

it('объясняет, как запустить источник без автопоиска', () => {
  const value = batch();
  value.sources = [{ code: 'myrunstats', status: 'unsupported', error: null }];
  value.drafts = [];

  render(
    <CollectionProgress
      batch={value}
      sourceLabel={() => 'MyRunStats'}
      starting={false}
      onStart={() => undefined}
    />,
  );

  expect(screen.getByText('Нужен код старта')).toBeTruthy();
  expect(
    screen.getByText(
      'Открой «Указать известные коды стартов», введи код для этого источника и нажми «Обновить данные».',
    ),
  ).toBeTruthy();
});
