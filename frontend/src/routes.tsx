// Таблица маршрутов. URL сохранены прежними (как у Jinja-страниц), чтобы не сломать ссылки.
// Новая страница: компонент в src/pages/, маршрут здесь, при необходимости — пункт в config/navigation.ts.
import { createBrowserRouter, type RouteObject } from 'react-router-dom';
import { AppLayout, type RouteHandle } from '@/components/layout/AppLayout';
import { NotFound } from '@/components/ui';
import { SearchPage } from '@/pages/SearchPage';
import { AthletePage } from '@/pages/AthletePage';
import { RatingPage } from '@/pages/RatingPage';
import { RatingFormulaPage } from '@/pages/RatingFormulaPage';
import { EventsPage } from '@/pages/EventsPage';
import { EventPage } from '@/pages/EventPage';
import { RacePage } from '@/pages/RacePage';
import { AgentReviewPage } from '@/pages/AgentReviewPage';

const handle = (h: RouteHandle) => h;

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <SearchPage />, handle: handle({ section: 'search', pageClass: 'page--narrow' }) },
      { path: '/athletes-view/:athleteId', element: <AthletePage />, handle: handle({ section: 'search' }) },
      { path: '/rating-view', element: <RatingPage />, handle: handle({ section: 'rating' }) },
      { path: '/rating-formula', element: <RatingFormulaPage />, handle: handle({ section: 'rating' }) },
      { path: '/events-view', element: <EventsPage />, handle: handle({ section: 'events' }) },
      { path: '/events-view/:eventId', element: <EventPage />, handle: handle({ section: 'events' }) },
      { path: '/races-view/:raceId', element: <RacePage />, handle: handle({ section: 'events' }) },
      { path: '/agent-review', element: <AgentReviewPage />, handle: handle({ section: 'agent' }) },
      { path: '*', element: <NotFound />, handle: handle({ section: 'search' }) },
    ],
  },
];

export const router = createBrowserRouter(routes);
