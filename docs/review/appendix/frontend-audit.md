# Аудит фронтенда (frontend/)

Дата: 2026-11-14. Объём: ~3 800 строк (из них `theme.css` 792, `types.ts` 270). Стек: React 18.3, Vite 5.4, TypeScript 5.6, React Router 6.28, Chart.js 4.4, Air Datepicker 3.5.

Проверки: `node_modules` в `frontend/` отсутствует, поэтому `npx tsc --noEmit` и `npm run build` НЕ запускались (по условию ничего не устанавливали). Результат ниже — статический разбор. `npm run build` = `tsc --noEmit && vite build`, так что при установленных зависимостях типы проверяются на каждой сборке.

## Общая оценка

Код заметно лучше типичного «ИИ-перенос»: strict включён, `any` нет, отмена запросов реализована, есть единая точка API-вызовов, дизайн-токены и тёмная тема работают, страницы разбиты на локальные подкомпоненты. Проблемы не в аккуратности, а в **отсутствии инфраструктуры**: нет линтера, тестов, CI, генерации типов, кэша запросов, code-splitting и правил структуры. Из-за этого каждый следующий экран будет копировать текущие паттерны вместе с их дефектами.

## Карта текущей структуры

```
frontend/
├── index.html                 инлайн-скрипт темы, шрифты с Google Fonts (CDN)
├── vite.config.ts             алиас @, прокси /api|/docs|/openapi.json, manualChunks
├── tsconfig.json              strict, noUnused*, paths @/*
├── package.json               5 prod-зависимостей, 6 dev; скрипты: dev/build/preview/typecheck
└── src/
    ├── main.tsx               StrictMode > ThemeProvider > RouterProvider
    ├── routes.tsx             createBrowserRouter, 8 страниц, импорты статические
    ├── config/navigation.ts   NAV_ITEMS
    ├── api/
    │   ├── client.ts          fetch-обёртка, ApiError, buildQuery
    │   ├── endpoints.ts       *Api-объекты по доменам
    │   └── types.ts           270 строк типов, написаны вручную
    ├── hooks/                 useApi (самописный), useDocumentTitle, keepScroll (константа)
    ├── lib/                   format.ts (даты/склонения/названия), markdown.ts
    ├── theme/ThemeProvider.tsx
    ├── components/
    │   ├── layout/AppLayout.tsx
    │   ├── ui/                index.tsx (8 компонентов в одном файле), Icon, DistancePills
    │   ├── charts/            useChart, PaceChart, DistributionChart
    │   ├── forms/             BirthYearInput, DateRangePicker
    │   └── athlete/AssessmentCard.tsx
    ├── pages/                 8 файлов, 84-310 строк, внутри 2-6 локальных компонентов
    └── styles/                theme.css (токены + компоненты), app.css (страницы), глобально
```

Размеры страниц: AgentReviewPage 310, RacePage 279, AthletePage 204, EventsPage 182, RatingPage 152, SearchPage 124, RatingFormulaPage 96, EventPage 84. Самый длинный компонент — `ReviewCard` (AgentReviewPage.tsx:117-310, ~190 строк, 8 `useState`).

## Таблица проблем

Severity: H — ломает поведение или блокирует развитие; M — накапливающийся долг; L — гигиена.

| # | Sev | Где | Что | Как правильно |
|---|-----|-----|-----|---------------|
| 1 | H | `hooks/useApi.ts:26-48` | При смене deps старые `data` не сбрасываются, `loading` не показывается пользователю (страницы проверяют `!data`). Переход athlete A → B показывает профиль A до прихода B. Нет кэша, дедупликации, retry, refetch on focus, общего состояния мутаций | TanStack Query: `useQuery` с `queryKey`, `placeholderData`/`keepPreviousData` осознанно, `useMutation` + `invalidateQueries` |
| 2 | H | `components/athlete/AssessmentCard.tsx:15-29`, `pages/AthletePage.tsx:23` | `AssessmentCard` остаётся смонтированным при смене `athleteId` (PageState не перемонтирует профиль), состояние `ready` с отчётом предыдущего спортсмена переживает навигацию. Запрос не отменяется при размонтировании | `key={athleteId}` на профиле либо `useMutation` с привязкой к id; отмена через signal |
| 3 | H | `api/types.ts` (весь файл, 270 строк) | Типы ручные, комментарий «при изменении модели обновите и этот файл». Бэкенд уже даёт `response_model` на всех GET/POST (`app/api/*.py`) и `/openapi.json`, т.е. дрейф неизбежен. Расхождения уже есть: `place_abs: number\|string` (`app/models.py:27`, у бэка `Union[int,str]` только в одном DTO, в остальных `int`), `[key: string]: unknown` в `AgentRun` (types.ts:228), типы agent-review описывают dict из `app/agent_review.py`, а не pydantic-модель; `post<unknown>` для decide/reset/remove (`endpoints.ts:45-48`) | `openapi-typescript` + `openapi-fetch` (или orval/hey-api), скрипт `gen:api` из `/openapi.json`, проверка актуальности в CI |
| 4 | H | весь `frontend/` | Нет eslint, prettier, тестов, CI (`.github/` отсутствует). В коде 3 `// eslint-disable-next-line react-hooks/exhaustive-deps` (`useApi.ts:50`, `useChart.ts:22`, `BirthYearInput.tsx:35`, `DateRangePicker.tsx:108`) — а плагина нет, прагмы мёртвые, а подавленные зависимости не проверяются никем | ESLint flat config (`typescript-eslint`, `react-hooks`, `jsx-a11y`, `boundaries`), Prettier, Vitest + RTL, CI: typecheck+lint+test+build |
| 5 | M | `pages/AgentReviewPage.tsx:35-36`, `:117-310` | После любого `decide/apply` вызывается `reload()` → `!data \|\| loading ? <Loader/>` заменяет весь список лоадером, все `ReviewCard` размонтируются, локальный ввод (комментарий, автор, чекбоксы) теряется. `ReviewCard` — 190 строк, 8 `useState`, смесь запросов, разметки, 3 вариантов футера; ручной `busy/removing/resetting/msg` вместо состояния мутации | Вынести `useReviewActions(issueId)` на `useMutation`; разметку разбить: `ReviewHeader`, `DiffView`, `ReviewDecisions`, `ReviewActions`; не заменять список лоадером при refetch |
| 6 | M | `AgentReviewPage.tsx:166, 186, 194, 150` | `setTimeout(onChanged, 2500)` без очистки (setState/запрос после размонтирования); `window.confirm`/`window.alert` вместо модалки; `navigate('/agent-review?status=proposed')` — литерал URL; `reset` молча глотает ошибку (`catch {}`); обязательность комментария при отклонении не валидируется на клиенте | Диалог-компонент, `useMutation.onSuccess`, роутинг через хелпер `paths`, показ ошибки |
| 7 | M | `pages/*` — 73 вхождения `style={{…}}` (AgentReview 19, RacePage 18, AthletePage 15, EventsPage 7, EventPage 6, Assessment 5, SearchPage 3) | Инлайн-стили с «магическими» числами (`minHeight: 40`, `padding: 20`, `fontSize: 15`, `minWidth: 760`), часть повторяется дословно (`flexDirection: 'column', gap: 12, padding: 20` в RacePage.tsx:115 и EventPage.tsx:40). Обходят токены и медиа-запросы, ломают единый ритм | Классы (CSS Modules) / утилиты; повторяющиеся сочетания — компоненты (`<HeroCard>`, `<Stat>`) |
| 8 | M | `RacePage.tsx:211-251`, `AthletePage.tsx:137-194`, `EventsPage.tsx:117-179` | Каждый список рендерится дважды: таблица (десктоп) + список (телефон), прячутся CSS-классами `only-desktop/only-mobile`. Двойной DOM, дублирование логики (`ProtocolTableRow`/`ProtocolListRow`, `isNewMonth`, подписи места), риск рассинхрона | Один источник данных + один компонент с адаптивной вёрсткой (CSS grid/container queries) либо `useMediaQuery` и рендер одного варианта |
| 9 | M | `routes.tsx:6-13`, `vite.config.ts:25-29` | Все страницы импортируются статически — Chart.js (≈200 КБ) и Air Datepicker грузятся на первом экране, хотя нужны только на `/athletes-view`, `/races-view`, `/events-view`. `manualChunks` лишь режет бандл на файлы, но не откладывает загрузку | `lazy()` на страницы (в RR6 — `lazy` в route object), `charts` и `datepicker` попадают в чанки страниц автоматически; убрать `manualChunks` для них |
| 10 | M | `pages/EventsPage.tsx:32-37`, `RatingPage.tsx:20-35`, `RacePage.tsx:16-31`, `SearchPage.tsx:19-21`, `AgentReviewPage.tsx:15-17` | URL-state парсится вручную в каждой странице (`params.get(...) \|\| ''`, `Number(...) \|\| null`, ручные `URLSearchParams`), без схемы и валидации; `filtersKey = ...join('\|')` как ручной ключ зависимостей; `readFilters` содержит алиас `title`→`query` | Общий `useUrlState(schema)` (zod) или `nuqs`; типизированные билдеры ссылок |
| 11 | M | `pages/*.tsx`: `RatingPage.tsx:63-65`, `EventsPage.tsx:60-63`, `SearchPage.tsx:83-84`, `AgentReviewPage.tsx:35-36` против `PageState` в `RacePage/AthletePage/EventPage/RatingFormulaPage` | Две реализации loading/error/empty: 4 страницы руками, 4 — через `PageState` (render-prop `children: () => ReactNode` + `data!` в `RacePage.tsx:36`, `AthletePage.tsx:23`, `EventPage.tsx:25`). `loading` при refetch в одних случаях прячет данные (Events, AgentReview), в других нет | Один паттерн: `QueryBoundary`/`Suspense + ErrorBoundary` либо `useQuery` + общий `<AsyncView query={q}>` с discriminated union без `!` |
| 12 | M | `styles/theme.css`, `styles/app.css`, `components/ui/index.tsx` | Весь стиль — два глобальных файла (792+114 строк), селекторы глобальны, размётка использует БЭМ-подобные классы (`list-row__title`, `rating-side-card__link`) но без изоляции; дубли токенов тёмной темы: `theme.css:61` (`:root:not([data-theme="light"])`) и `:98` (`[data-theme="dark"]`); `app.css` содержит правки «чтобы вёрстка совпала с Jinja» (quirks-mode `.table--legacy-metrics`) — долг переноса | CSS Modules на компонент, токены остаются в `theme.css` (дубль тёмной темы свести через `color-scheme`/один блок); legacy-метрики таблиц — отдельная задача удаления |
| 13 | M | `pages/RatingFormulaPage.tsx:10-18`, `components/charts/PaceChart.tsx:7-21`, `lib/format.ts:35-50`, `RatingPage.tsx:11-15, 45-48`, `RacePage.tsx:173` | Магические строки и справочники в компонентах: названия дистанций дублируются в двух местах (`DISTANCE_TITLES`, `NORM_SHORT`), `SOURCE_NAMES`/`SOURCE_KEYS` вручную (источники `probeg`, `grom` в одном списке, но не в другом), «365 дней» зашито в 2 страницах, виды спорта «Лыжи/Триатлон/Трейл» — хардкод в JSX. Типы `status: string`, `gender: string` — без union | Единый `shared/config` (дистанции, площадки, периоды), литеральные union из OpenAPI-enum, названия приходят с бэка |
| 14 | M | `components/ui/index.tsx` (99 строк, 8 компонентов), `PageState` | Файл-«свалка»: `BackLink`, `StatusChip`, `EmptyState`, `Loader`, `ErrorState`, `NotFound`, `PageState`, `GapDots`; barrel `index.tsx` со смесью реэкспортов и реализаций. `GapDots` не используется (в RacePage.tsx:229, 245 и RatingPage.tsx:120 вручную `&bull;<br/>`). `countLabel` в `format.ts:74` нигде не применяется | По файлу на компонент, barrel только реэкспорт; удалить неиспользуемое (включить `knip`/`no-unused-exports`) |
| 15 | M | `components/charts/useChart.ts:18-24`, `PaceChart.tsx:41-126`, `DistributionChart.tsx` | Графики пересоздаются целиком при любом изменении deps/темы (`chart.destroy()` + `new Chart`), нет `chart.update()`; `themeToken()` читает CSS через `getComputedStyle` синхронно в билдере (зависимость от порядка эффектов темы); `axisCaption as Plugin` — каст; конфиг на 85 строк внутри компонента, смешан с вычислением labels | `react-chartjs-2` либо обновлять `chart.data` + `update()`; конфигурация и подготовка данных — чистые функции вне компонента (тестируемы) |
| 16 | M | `components/forms/BirthYearInput.tsx` (90 строк), `DateRangePicker.tsx` (120 строк) | Императивная обвязка над DOM: нативные слушатели, `document.addEventListener('click', …, true)`, определение клика по «правым 35px» поля для стрелок number-input, мутация `input.value` вручную (`DateRangePicker.tsx:63-97`), `readOnly` поле даты: для скринридера и клавиатуры это тупик; пересоздание календаря через `key` формы | `<input type="date">`/две даты нативно (или `react-day-picker`); для года — `type="text" inputMode="numeric" pattern`, без перехвата стрелок |
| 17 | M | `index.html:14-17` | Шрифты с `fonts.googleapis.com` (CDN): внешняя зависимость и приватность (РФ-аудитория, возможные блокировки), FOUT, нет `font-display` контроля | `@fontsource/golos-text`, `@fontsource/unbounded` (self-host) |
| 18 | L | `AssessmentCard.tsx:62`, `RacePage.tsx:210,239`, `EventsPage.tsx:116,160`, `RatingPage.tsx:90,104`, `SearchPage.tsx:31`, `useChart.ts`, `DistancePills.tsx` и др. | Комментарии-пересказы и блочные баннеры в JSX, противоречат правилу «ноль комментариев»; в шапках файлов — история переноса из Jinja («Перенос race_detail.html») — это место для коммита/ADR | Удалить, оставить только «почему» |
| 19 | L | `api/client.ts:25-38, 40-44` | `request` не учитывает не-JSON ответы (204, текст), `res.json().catch(() => null)` маскирует ошибки; `data as T` — доверие без валидации; POST/DELETE без `signal`; нет таймаута; `typeof data.detail === 'string'` — FastAPI 422 отдаёт массив `detail`, и сообщение теряется («ошибка 422»); нет базового URL из env | `openapi-fetch` + middleware ошибок; разбор 422 (`detail[].msg`); `VITE_API_BASE_URL` |
| 20 | L | `components/ui/DistancePills.tsx`, `AppLayout.tsx` | a11y: нет skip-link, нет управления фокусом/анонса при смене маршрута (SPA), `aria-current="page"` на ссылках фильтра дистанций (семантически это не «страница»); `Link` с `onClick preventDefault` как кнопка сброса (`EventsPage.tsx:103`); `rating-sport--disabled` — `span` без `aria-disabled`; графики — только `canvas role="img"` без текстовой альтернативы/таблицы | skip-link, `document.title`+focus на `<h1>` при навигации, `<button>` для действий, `aria-disabled`, `<table>`-fallback графика |
| 21 | L | `hooks/keepScroll.ts` | Файл хука, а содержимое — константа; логика «prevent scroll reset» размазана между `KEEP_SCROLL` и `preventScrollReset` в `<Link>` | Положить в `shared/lib/router`, либо обернуть в `useUrlState` |
| 22 | L | `api/endpoints.ts:10,26` | `limit: 50`/`limit: 60` зашиты; нет пагинации/бесконечного списка (события — 60 максимум, рейтинг — `1–N из total` без «ещё») | Пагинация или «показать ещё» (`useInfiniteQuery`) |
| 23 | L | `package.json` | Версии зафиксированы без `^` (хорошо), но нет `engines`, `lint`, `test`, `format` скриптов; в `devDependencies` `@types/node` ради `vite.config.ts` | Добавить `engines`, `lint`, `test`, `format`, `gen:api` |

## Детали по запрошенным разделам

**Типизация.** `strict: true`, `noUnusedLocals/Parameters`, `noFallthroughCasesInSwitch`, `isolatedModules` — хорошо. Не хватает `noUncheckedIndexedAccess` и `exactOptionalPropertyTypes` (включить поэтапно). `any` нет; касты: `api/client.ts:37` (`data as T`), `AppLayout.tsx:17` (`m.handle as RouteHandle`), `DateRangePicker.tsx:83`, `PaceChart.tsx:76`, `firstDay: 1 as const`. Non-null assertions `data!`: `RacePage.tsx:36`, `AthletePage.tsx:23`, `EventPage.tsx:25`, `format.ts:18`, `main.tsx:10`. Типы API вручную; бэкенд FastAPI с `response_model` — генерация возможна без изменений бэка (за исключением `post<unknown>` у agent-review: нужен `response_model`).

**Data fetching.** Самописный `useApi` корректно отменяет запросы (AbortController, проверка `aborted`, игнор `AbortError`) — гонок «поздний ответ перетёр новый» нет. Но: нет кэша (возврат на страницу = новый запрос + лоадер), нет дедупликации (StrictMode в dev дважды дёргает API), нет `stale-while-revalidate`, нет retry, мутации — вручную в компонентах (`AgentReviewPage`, `AssessmentCard`) без `signal`, без инвалидации. `AthletePage` объединяет два запроса через `Promise.all` — один упавший ломает оба; результат — кортеж `data[0]/data[1]` (нечитаемо).

**Состояние.** Серверное — в `useApi`; URL-state — `useSearchParams` на каждой странице вручную (хорошо, что фильтры в URL: ссылки шарятся); формы — локальный `useState` + синхронизация через `key={params.toString()}` (хак пересоздания формы); глобальное — только тема (Context, корректно, мемоизирован). Глобального стора нет и он не нужен.

**Стили.** Plain CSS, глобальный, токены CSS-переменных (`:root`, `[data-theme]`), БЭМ-подобные имена, 73 инлайн-стиля, 7+2 `!important`, 8 медиа-запросов. Тёмная тема работает через токены + инлайн-скрипт до отрисовки (нет мигания) — это сильная сторона. Дублирование: блок тёмных токенов (2 места), повтор flex-колонок через inline.

**Роутинг/сплиттинг.** `createBrowserRouter` (data router без loaders/actions — возможности RR6 не используются: данные грузятся в эффектах → «водопад»: JS → рендер → fetch). Нет `errorElement` на маршрутах (исключение в рендере = белый экран), нет lazy.

**Графики.** Chart.js 4 напрямую, tree-shaking регистрацией компонентов (`useChart.ts:10`) — правильно.

**Производительность.** Нет `React.memo`/`useMemo` там, где они нужны не сильно: списки ≤60/50 строк. Риски: двойной DOM (п. 8), протокол дистанции без пагинации/виртуализации (`RacePage` рендерит все `results`), пересоздание графиков.

**Tooling.** Нет eslint/prettier/vitest/CI/husky; алиас `@` настроен в двух местах (tsconfig + vite) — ок; env: только `BACKEND_URL` для dev-прокси, `VITE_*` нет; `.gitignore` минимальный (нет `.env*`, `coverage`).

## Что уже сделано хорошо (сохранить)

- Единая точка вызовов `api/endpoints.ts`, `AbortSignal` во всех GET.
- `strict` TS, отсутствие `any`.
- Токены дизайн-системы и тема без мигания (ADR-0001, ThemeProvider).
- URL — источник истины для фильтров, `preventScrollReset` продуман.
- Локальные подкомпоненты в страницах, `PageState` как попытка единой обработки состояний.
- Безопасный рендер Markdown (экранирование до подстановки, `lib/markdown.ts:6`) — но см. ниже.

Замечание по `lib/markdown.ts`: самописный regex-рендер ограничен (нет списков `<ul>`, `<li>` без родителя; `<p></p>` вместо абзацев). Если отчёты будут богаче — `react-markdown` без `dangerouslySetInnerHTML`.

## Приоритеты исправления

1. Инфраструктура: ESLint+Prettier+Vitest+CI, `gen:api` (п. 3, 4).
2. TanStack Query вместо `useApi` (п. 1, 2, 5, 6, 11).
3. Code-splitting, `errorElement`, self-host шрифтов (п. 9, 17).
4. Стили: Modules + убрать inline (п. 7, 12).
5. Единые справочники и компоненты списков (п. 8, 13, 14).
