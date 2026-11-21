import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { expect, it } from 'vitest';
import { server } from '../../../tests/server';
import { SearchResults } from './SearchResults';

const url = 'http://localhost:5173/api/athletes/search';
function search() {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={cache}>
      <MemoryRouter>
        <SearchResults lastName="Иванов" birthYear={1990} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it('показывает загрузку и пустой результат', async () => {
  server.use(http.get(url, () => HttpResponse.json([])));
  search();
  expect(screen.getByRole('status').textContent).toContain('Ищем спортсменов');
  expect(await screen.findByRole('heading', { name: 'Никого не нашли' })).toBeTruthy();
});

it('объясняет ошибку валидации и повторяет поиск с исходными фильтрами', async () => {
  server.use(
    http.get(url, () =>
      HttpResponse.json(
        { detail: [{ loc: ['query', 'birth_year'], msg: 'Некорректный год' }] },
        { status: 422 },
      ),
    ),
  );
  search();
  expect((await screen.findByRole('alert')).textContent).toContain('birth_year: Некорректный год');
  server.use(
    http.get(url, ({ request }) => {
      const q = new URL(request.url).searchParams;
      if (q.get('last_name') !== 'Иванов' || q.get('birth_year') !== '1990') return HttpResponse.error();
      return HttpResponse.json([{ id: 7, display_name: 'Иван Иванов', starts_count: 3, results_count: 3 }]);
    }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  expect(await screen.findByText('Иван Иванов')).toBeTruthy();
  expect(screen.getByRole('link').getAttribute('href')).toBe('/athletes-view/7');
});
