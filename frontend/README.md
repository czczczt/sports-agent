# Веб-интерфейс (React)

Публичная часть платформы и экран правок агента. React 18 + TypeScript + Vite 5, React Router 6, Chart.js, Air Datepicker.
Почему так и чем отличается от прежних Jinja-шаблонов — [ADR-0002](../docs/adr/0002-react-frontend.md); дизайн-система — [ADR-0001](../docs/adr/0001-frontend-design-system.md).

## Запуск

Нужен Node.js 18+ и запущенный бэкенд (`python -m uvicorn app.main:app --port 8000` из корня репозитория).

```bash
npm --prefix frontend install
npm --prefix frontend run dev        # http://localhost:5173, /api проксируется на :8000
```

Другой адрес бэкенда: `BACKEND_URL=http://127.0.0.1:8001 npm --prefix frontend run dev`.

Сборка для FastAPI (сервер раздаёт `frontend/dist` на тех же адресах, что и раньше — http://localhost:8000/):

```bash
npm --prefix frontend run build      # tsc --noEmit + vite build → frontend/dist
```

`npm run typecheck` — только проверка типов.

## Структура

```
frontend/
├── index.html                 каркас: шрифты, инлайн-скрипт темы (до отрисовки, без мигания)
├── vite.config.ts             алиас @ → src, прокси /api → бэкенд, чанки react/charts/datepicker
└── src/
    ├── main.tsx               точка входа: ThemeProvider + RouterProvider, подключение CSS
    ├── routes.tsx             таблица маршрутов (URL как у прежних страниц) + handle: раздел меню, класс страницы
    ├── config/navigation.ts   пункты верхнего и нижнего меню
    ├── api/
    │   ├── client.ts          fetch-обёртка, ApiError(status, detail)
    │   ├── endpoints.ts       все запросы к бэкенду
    │   └── types.ts           типы ответов (копия pydantic-моделей app/models.py)
    ├── hooks/
    │   ├── useApi.ts          загрузка данных страницы с отменой устаревших запросов
    │   └── useDocumentTitle.ts
    ├── theme/ThemeProvider.tsx  тема Системная/Светлая/Тёмная, themeToken() для canvas
    ├── lib/
    │   ├── format.ts          даты, время, склонения, площадки (бывшие макросы _ui.html)
    │   └── markdown.ts        безопасный рендер отчёта ИИ-оценки
    ├── components/
    │   ├── layout/AppLayout.tsx   шапка, <main class="page">, подвал, нижняя панель
    │   ├── ui/                    Icon, BackLink, StatusChip, EmptyState, Loader, ErrorState, NotFound, PageState
    │   ├── charts/                useChart (Chart.js + перерисовка при смене темы), PaceChart, DistributionChart
    │   ├── forms/                 BirthYearInput, DateRangePicker
    │   └── athlete/AssessmentCard.tsx
    ├── pages/                 по файлу на страницу
    └── styles/
        ├── theme.css          дизайн-система (ADR-0001), перенесена без изменений
        └── app.css            стили отдельных страниц и правки для React-версии
```

## Как добавить страницу

1. **API.** Эндпоинт на бэкенде (`app/api/...`, подключается в `app/main.py` в роутер `/api`), функция в `src/api/endpoints.ts`, тип ответа в `src/api/types.ts`.
2. **Страница.** `src/pages/NewPage.tsx`:
   ```tsx
   export function NewPage() {
     useDocumentTitle(`Новый раздел — ${SITE_TITLE}`);
     const { data, error, loading, reload } = useApi((signal) => someApi.get(signal), []);
     return (
       <PageState loading={loading} error={error} hasData={!!data} onRetry={reload}>
         {() => <section className="card card--pad">…</section>}
       </PageState>
     );
   }
   ```
3. **Маршрут** в `src/routes.tsx`: `{ path: '/new-view', element: <NewPage />, handle: handle({ section: 'new' }) }`.
4. **Меню** (если нужно): пункт в `src/config/navigation.ts` и значение в типе `Section`. `mobile: true` — показать и в нижней панели на телефоне (колонки подстраиваются под число пунктов).
5. **Вёрстка** — только классы `theme.css` (`.card`, `.btn`, `.chip`, `.table`, `.list-row`, `.tile`, `.only-desktop`/`.only-mobile` …) и токены цветов. Своё — в `app.css` с комментарием, к какой странице относится.

Состояние фильтров и поиска держите в query-параметрах (`useSearchParams`), а не в памяти компонента: так ссылку можно отправить, а «Назад» в браузере работает.
