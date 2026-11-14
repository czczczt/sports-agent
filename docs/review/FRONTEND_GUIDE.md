# Гид по фронтенду на React

Свод правил и практик фронтенд-разработки для разработчиков и AI-агентов. Примеры доменные (спорт), правила не привязаны к проекту.

Формат: правило, почему (где неочевидно), пример. Код в примерах без комментариев-пересказов.

## Оглавление

1. Стек
2. Принципы
3. Структура: FSD-lite
4. Компоненты
5. Хуки
6. Состояние: что где хранить
7. Работа с API
8. Стили
9. Типизация
10. Загрузка, ошибки, пустые состояния
11. Формы
12. Доступность
13. Роутинг и производительность
14. Тесты
15. Комментарии и стиль кода
16. Чек-лист PR и правила для AI-агента

---

## 1. Стек

| Задача | Выбор | Почему |
|---|---|---|
| Сборка | Vite | Быстрый dev-сервер, простой конфиг |
| Язык | TypeScript `strict` | Ошибки контракта ловятся до рантайма |
| Роутинг | React Router 7 | Стандарт, `lazy` и `errorElement` из коробки |
| Серверные данные | TanStack Query | Кэш, дедупликация, отмена, retry, фоновое обновление |
| Типы и клиент API | `openapi-typescript` + `openapi-fetch` | Типы генерируются из OpenAPI бэкенда, ручных интерфейсов нет |
| Стили | CSS Modules + CSS-переменные (токены) | Нативный CSS, изоляция классов, тема через переменные |
| Формы | `useState` / react-hook-form + zod | Простое просто, сложное с валидацией по схеме |
| Глобальный стейт | Context; Zustand только при реальной нужде | Большая часть «глобального» — это сервер или URL |
| Линт и формат | ESLint (flat) + `eslint-plugin-boundaries` + `jsx-a11y` + Prettier | Границы слоёв и доступность проверяются автоматически |
| Тесты | Vitest + Testing Library + MSW, Playwright для e2e | Тестируем поведение, сеть подменяем |

Скрипты `package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "typecheck": "tsc --noEmit",
    "lint": "eslint . --cache --cache-location node_modules/.cache/eslint/",
    "format": "prettier --write .",
    "test": "vitest run",
    "gen:api": "openapi-typescript http://localhost:8000/openapi.json -o src/shared/api/schema.d.ts"
  }
}
```

## 2. Принципы

1. Код простой и скучный: понятные имена важнее комментариев.
2. Один источник истины: типы API — из OpenAPI, цвета и отступы — из токенов, фильтры — из URL, данные сервера — из Query.
3. Зависимости идут в одну сторону (раздел 3); нарушение ловит линтер.
4. Перед PR: `npm run typecheck && npm run lint && npm run test && npm run build`.
5. Не знаешь, куда положить код, — положи в ближайшую фичу; не создавай новую «общую» папку.

## 3. Структура: FSD-lite

Упрощённый Feature-Sliced Design: четыре слоя вместо семи. Слои `entities/` и `widgets/` добавляются, только когда появляется реальное переиспользование (см. ниже).

```
src/
  app/
    providers.tsx            QueryClientProvider, ThemeProvider, RouterProvider
    router.tsx               таблица маршрутов, lazy-страницы, errorElement
    styles/                  tokens.css, global.css (reset, типографика)
  pages/
    rating/
      RatingPage.tsx         композиция фич, без запросов
      RatingPage.module.css
      index.ts
    athlete/
    events/
  features/
    rating-table/
      ui/RatingTable.tsx
      ui/RatingTable.module.css
      model/useRating.ts     useQuery, ключи, маппинг
      api/ratingApi.ts       тонкие функции над клиентом
      index.ts               публичный API слайса
    athlete-search/
    events-filter/
  shared/
    api/
      client.ts              openapi-fetch, обработка ошибок
      schema.d.ts            генерируется (gen:api), не править
    ui/                      Button, Card, Table, EmptyState, Spinner, AsyncView
    lib/                     format, plural, url-state
    config/                  paths, справочники
    hooks/                   useDocumentTitle, useMediaQuery
```

Правила слоёв:

- Импорт только вниз: `app → pages → features → shared`. `shared` ничего не знает о фичах.
- Фича не импортирует другую фичу; общее поднимается в `shared` или собирается в `pages`.
- Снаружи слайса импортируется только его `index.ts` (`@/features/rating-table`, не `@/features/rating-table/ui/RatingTable`).
- Алиас `@/` → `src/`. Относительные пути — только внутри одного слайса.
- Слайс держит рядом компонент, `*.module.css`, тесты `*.test.tsx`, хуки, типы.
- Страница тонкая: читает URL, собирает фичи, задаёт `document.title`. Запросов и сложной логики в ней нет.

Когда расширять до полного FSD:

| Признак | Что добавить |
|---|---|
| Одна бизнес-сущность (карточка спортсмена, бейдж результата) нужна двум и более фичам | `entities/<entity>/` между `features` и `shared` |
| Один и тот же составной блок из нескольких фич повторяется на разных страницах | `widgets/<widget>/` между `pages` и `features` |

Проверка границ — `eslint-plugin-boundaries` (+ `eslint-import-resolver-typescript` для алиаса `@/`):

```js
export default [
  {
    settings: {
      'import/resolver': { typescript: true },
      'boundaries/elements': [
        { type: 'app', pattern: 'src/app' },
        { type: 'pages', pattern: 'src/pages/*' },
        { type: 'features', pattern: 'src/features/*' },
        { type: 'shared', pattern: 'src/shared/*' },
      ],
    },
    rules: {
      'boundaries/element-types': ['error', {
        default: 'disallow',
        rules: [
          { from: 'app', allow: ['pages', 'features', 'shared'] },
          { from: 'pages', allow: ['features', 'shared'] },
          { from: 'features', allow: ['shared'] },
          { from: 'shared', allow: ['shared'] },
        ],
      }],
      'boundaries/entry-point': ['error', {
        default: 'disallow',
        rules: [{ target: ['pages', 'features', 'shared'], allow: 'index.(ts|tsx)' }],
      }],
    },
  },
];
```

## 4. Компоненты

- Один экспортируемый компонент на файл, имя файла = имя компонента (`PascalCase.tsx`).
- Ориентир размера: ≤ 150 строк, ≤ 5 `useState`, ≤ 7 props. Превышение — повод выделить хук или подкомпонент.
- Props — явный `interface XxxProps`, без `any`, без «режимов» из 4+ булевых флагов; вместо флагов — `children`/слоты.
- Компонент либо получает данные (хук внутри) и рендерит, либо чисто презентационный. Не смешивать запросы, преобразование данных и 100 строк разметки.
- `key` — стабильный id, не индекс.
- Состояние дочернего блока, привязанное к сущности, сбрасывается сменой `key={entityId}`.
- Адаптивность — CSS, а не два набора разметки для одних данных.
- Тексты и справочники — из `shared/config`, а не строки в JSX.

Страница тонкая, данные в хуке фичи:

```tsx
export function RatingPage() {
  useDocumentTitle('Рейтинг');
  const { gender, athleteId, setGender } = useRatingFilters();

  return (
    <div className={styles.page}>
      <RatingHeader />
      <GenderSwitch value={gender} onChange={setGender} />
      <RatingTable gender={gender} highlightAthleteId={athleteId} />
    </div>
  );
}
```

Компонент фичи со всеми состояниями:

```tsx
export function RatingTable({ gender, highlightAthleteId }: RatingTableProps) {
  const query = useRating({ gender, athleteId: highlightAthleteId });

  return (
    <AsyncView query={query} empty={<EmptyState title="Рейтинг пока пуст" />}>
      {(data) => <RatingRows rows={data.rows} highlightAthleteId={highlightAthleteId} />}
    </AsyncView>
  );
}
```

## 5. Хуки

- Имя начинается с `use`, один хук — одна ответственность.
- Выносить хук, если логика не про разметку и длиннее ~15 строк либо нужна повторно.
- Хук не возвращает JSX. Возвращает объект с понятными полями, а не массив из 4 элементов.
- Эффекты — только для синхронизации с внешним миром (DOM, подписки, таймеры). Запросы — не в `useEffect`.
- Каждый эффект с подпиской или таймером возвращает очистку.
- `react-hooks/exhaustive-deps` — `error`. Подавление — только с `// почему:`.

## 6. Состояние: что где хранить

| Что | Где |
|---|---|
| Данные с сервера | TanStack Query (`useQuery`, `useMutation`) |
| Фильтры, страница, сортировка | URL (search params) через `useUrlState` |
| Черновик формы | `useState` (1-3 поля) или react-hook-form + zod |
| Эфемерное UI-состояние (раскрыто, busy) | `useState` рядом с компонентом |
| Тема, пользователь, локаль | Context |
| Клиентское состояние, общее для многих экранов и не лежащее в URL/сервере | Zustand |

Запрещено: копировать данные из Query в `useState` или стор; хранить фильтры в `useState`, если они должны переживать reload и шаринг ссылки.

## 7. Работа с API

- Типы — только из `shared/api/schema.d.ts`. Ручные интерфейсы ответов не пишем. Обновить: `npm run gen:api`.
- Бэкенд обязан отдавать `response_model` у каждого эндпоинта, иначе тип ответа не сгенерируется.
- Вызовы — через `shared/api/client.ts`; прямой `fetch`/`axios` в компонентах запрещён.

```ts
import createClient from 'openapi-fetch';
import type { paths } from './schema';

export const api = createClient<paths>({ baseUrl: import.meta.env.VITE_API_URL });
```

- Чтение — `useQuery` в хуке фичи; ключи — фабрика, а не строки по месту:

```ts
export const ratingKeys = {
  all: ['rating'] as const,
  page: (params: RatingParams) => [...ratingKeys.all, 'page', params] as const,
};

export function useRating(params: RatingParams) {
  return useQuery({
    queryKey: ratingKeys.page(params),
    queryFn: ({ signal }) => ratingApi.page(params, signal),
    placeholderData: keepPreviousData,
  });
}
```

- Запись — `useMutation`, после успеха — `invalidateQueries`:

```ts
export function useArchiveEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (eventId: number) => eventsApi.archive(eventId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: eventKeys.all }),
  });
}
```

- Ошибки API превращаются в `ApiError` в одном месте (клиент); ответ 422 разбирается в читаемое сообщение.
- Отмена — через `signal` из `queryFn`; ручной `AbortController` не пишем.
- Retry, `staleTime`, `gcTime` — настройки `QueryClient`, не в компонентах.

## 8. Стили

- Стиль компонента — `Component.module.css` рядом. Глобальные селекторы только в `app/styles`.
- Цвета, отступы, радиусы, тени — только токены (`var(--…)`) из `tokens.css`. Литералы `#fff`, `16px` для цвета и ритма запрещены.
- Тёмная тема — через переопределение токенов (`[data-theme='dark']`); в компонентах нет `if (theme === 'dark')`.
- Инлайн `style={{…}}` — только для динамических значений (ширина полосы по данным).
- Классы в модулях — `camelCase` (`styles.rowActive`), состояния — `data-*` атрибутами.
- Брейкпоинты — из токенов, не новые числа в каждом файле.
- Анимации уважают `prefers-reduced-motion`.

```css
.row {
  display: grid;
  grid-template-columns: 3rem 1fr auto;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
}

.row[data-active] {
  background: var(--brand-soft);
}
```

## 9. Типизация

- `strict: true` и `noUncheckedIndexedAccess: true`.
- Запрещено: `any`, `@ts-ignore`, non-null `!`. `as` — только для `as const` или после сужения типа.
- `@ts-expect-error` — только с `// почему:`.
- Union вместо `string` для конечных наборов (`'M' | 'F'`, статусы) — из схемы OpenAPI.
- Внешние данные (URL, localStorage) валидируются zod до использования.
- Экспортируемые функции — с явным типом возврата.

```ts
const searchSchema = z.object({
  gender: z.enum(['M', 'F']).nullable().catch(null),
  athleteId: z.coerce.number().int().positive().nullable().catch(null),
});
```

## 10. Загрузка, ошибки, пустые состояния

Каждый экран с данными показывает четыре состояния: загрузка, ошибка (с повтором), пусто, данные. Используем единый `AsyncView`:

```tsx
export function AsyncView<T>({ query, empty, children }: AsyncViewProps<T>) {
  if (query.isPending) return <Spinner />;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;
  if (isEmpty(query.data)) return <>{empty}</>;
  return <>{children(query.data)}</>;
}
```

- 404 от API — экран «не найдено», а не общий текст ошибки.
- Повторная загрузка не заменяет данные спиннером: старые данные + индикатор (`isFetching`).
- На маршрутах — `errorElement`: ошибка рендера не даёт белый экран.
- Ошибки мутаций показываем пользователю; пустой `catch {}` запрещён.
- Подтверждение опасных действий — диалог-компонент, не `window.confirm`.

## 11. Формы

- Одно-три поля без сложной валидации: контролируемые `useState`.
- Больше — react-hook-form + zod (тип формы через `z.infer`).
- Фильтры, меняющие URL, берут начальные значения из URL.
- Каждое поле — `<label>` + `id`, ошибка — `aria-describedby`, `required`/`inputMode`/`autoComplete` по смыслу.
- Нативные контролы (`type="date"`, `select`) предпочтительнее библиотечных; библиотеку берём, только если нативный не закрывает задачу.
- Не перехватывать клавиши ради «улучшения» стандартных инпутов.

## 12. Доступность

- `button` для действий, `a`/`Link` для навигации.
- Один `h1` на страницу, заголовки по порядку, таблицы с `<th scope>`, `aria-label` у иконок-кнопок.
- Видимый `:focus-visible`; skip-link «К содержимому».
- Графики: `role="img"` + `aria-label` + текстовая альтернатива.
- Контраст ≥ 4.5:1 в обеих темах; информация не только цветом.
- `jsx-a11y` в ESLint — `error`.

## 13. Роутинг и производительность

- Страницы подключаются через `lazy`; тяжёлые библиотеки (графики, календари) попадают в чанк страницы.
- Пути — билдеры в `shared/config/paths.ts` (`paths.athlete(id)`), не строки по месту.
- Сотни элементов и больше — пагинация или «показать ещё».
- `memo`/`useMemo`/`useCallback` — только после измерения.
- Шрифты self-host (`@fontsource/*`), без внешних CDN.

## 14. Тесты

- Vitest + Testing Library: проверяем поведение, запросы по роли/тексту (`getByRole`).
- Сеть — MSW; реальных запросов в тестах нет.
- Обязательно: чистые функции, хуки с логикой, четыре состояния ключевых компонентов, формы.
- Playwright: 3-5 сквозных сценариев основных пользовательских путей.
- Баг-фикс начинается с падающего теста.

```tsx
it('показывает пустое состояние, если рейтинг пуст', async () => {
  server.use(http.get('/api/v1/rating', () => HttpResponse.json(emptyRating)));
  render(<RatingTable gender={null} highlightAthleteId={null} />);
  expect(await screen.findByText('Рейтинг пока пуст')).toBeInTheDocument();
});
```

## 15. Комментарии и стиль кода

- Комментариев нет. Разрешены: прагмы (`// eslint-disable-next-line …`, `// @ts-expect-error`), `TODO`/`FIXME` с конкретикой, `// почему: …` когда причина не выводится из кода.
- Запрещены: пересказ кода, баннеры-разделители, история изменений, закомментированный код.
- JSDoc — только на публичном API `shared`.
- Форматирование — Prettier.
- Именование: компоненты `PascalCase`, хуки `useXxx`, константы `UPPER_SNAKE`, утилиты `camelCase.ts`, стили `Component.module.css`.

---

## 16. Чек-лист PR и правила для AI-агента

### 16.1 Чек-лист PR

- [ ] `typecheck`, `lint`, `test`, `build` зелёные; `gen:api` не даёт diff.
- [ ] Границы слоёв не нарушены; импорт слайсов только через `index.ts`.
- [ ] Данные сервера через Query, фильтры в URL, нет копий в `useState`.
- [ ] Все четыре состояния экрана показаны.
- [ ] Нет `any`, `!`, `@ts-ignore`, `console.log`, инлайн-стилей для статики, литералов цветов.
- [ ] Компоненты ≤ ~150 строк, нет дублирования разметки.
- [ ] Доступность: клавиатура, подписи, фокус, контраст.
- [ ] Тест на новую логику; баг — с регрессионным тестом.

### 16.2 Правила для AI-агента

1. Перед правкой прочитай этот гид и соседние файлы слайса; повторяй существующие паттерны.
2. Код клади по слоям FSD-lite; импорт только вниз и только через `index.ts`.
3. Не добавляй зависимости без запроса; `schema.d.ts` не правь руками — запусти `gen:api`.
4. Не создавай файлы-свалки (`utils.ts`, `helpers.ts`, `common/`).
5. Запросы — только через клиент и `useQuery`/`useMutation`; никакого `fetch` в компонентах и `useEffect` для загрузки.
6. Фильтры, пагинация, сортировка — в URL; серверные данные — не в `useState`.
7. Стили — CSS Modules и токены; без инлайн-стилей и литералов цветов.
8. Без `any`, `!`, `as` для обхода ошибок типов; типы сужай.
9. Компонент больше ~150 строк или с 5+ `useState` — раздели на хук и подкомпоненты.
10. Комментарии: ноль, кроме прагм, `TODO` и `// почему:`.
11. В конце прогони `typecheck`, `lint`, `test`, `build`; не заявляй «работает», не запустив.
