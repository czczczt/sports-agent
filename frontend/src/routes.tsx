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
import { ResetPasswordPage } from '@/pages/ResetPasswordPage';
import { AdminRequestsPage } from '@/pages/AdminRequestsPage';
import { StatusPage } from '@/pages/StatusPage';

const handle = (h: RouteHandle) => h;

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <SearchPage />, handle: handle({ section: 'search', pageClass: 'page--narrow' }) },
      { path: '/status', element: <StatusPage />, handle: handle({ section: 'status', isPublic: true }) },
      { path: '/reset-password', element: <ResetPasswordPage />, handle: handle({ section: 'search', pageClass: 'page--narrow', isPublic: true }) },
      { path: '/athletes-view/:athleteId', element: <AthletePage />, handle: handle({ section: 'search' }) },
      { path: '/rating-view', element: <RatingPage />, handle: handle({ section: 'rating' }) },
      { path: '/rating-formula', element: <RatingFormulaPage />, handle: handle({ section: 'rating' }) },
      { path: '/events-view', element: <EventsPage />, handle: handle({ section: 'events' }) },
      { path: '/events-view/:eventId', element: <EventPage />, handle: handle({ section: 'events' }) },
      { path: '/races-view/:raceId', element: <RacePage />, handle: handle({ section: 'events' }) },
      { path: '/admin/requests', element: <AdminRequestsPage />, handle: handle({ section: 'admin' }) },
      { path: '/admin', element: <AdminRequestsPage />, handle: handle({ section: 'admin' }) },
      { path: '/agent-review', element: <AgentReviewPage />, handle: handle({ section: 'agent' }) },
      { path: '*', element: <NotFound />, handle: handle({ section: 'search' }) },
    ],
  },
];

export const router = createBrowserRouter(routes);
