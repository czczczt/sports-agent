import { routes as routePaths } from '@/shared/config';
import { ErrorState, Loader, NotFound } from '@/shared/ui';
import { createBrowserRouter, useRouteError, type RouteObject } from 'react-router-dom';
import { AppLayout, type RouteHandle } from './AppLayout';

function RouteError(): React.JSX.Element {
  const error = useRouteError();
  return (
    <main className="page">
      <ErrorState
        error={error instanceof Error ? error : new Error('Не удалось открыть страницу')}
        onRetry={() => window.location.reload()}
      />
    </main>
  );
}

const handle = (h: RouteHandle) => h;

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    hydrateFallbackElement: <Loader />,
    errorElement: <RouteError />,
    children: [
      {
        path: routePaths.search,
        lazy: () => import('@/pages/search'),
        handle: handle({ section: 'search', pageClass: 'page--narrow' }),
      },
      {
        path: routePaths.status,
        lazy: () => import('@/pages/status'),
        handle: handle({ section: 'status', isPublic: true }),
      },
      {
        path: routePaths.resetPassword,
        lazy: () => import('@/pages/reset-password'),
        handle: handle({ section: 'search', pageClass: 'page--narrow', isPublic: true }),
      },
      {
        path: routePaths.athlete,
        lazy: () => import('@/pages/athlete'),
        handle: handle({ section: 'search' }),
      },
      {
        path: routePaths.rating,
        lazy: () => import('@/pages/rating'),
        handle: handle({ section: 'rating' }),
      },
      {
        path: routePaths.ratingFormula,
        lazy: () => import('@/pages/rating-formula'),
        handle: handle({ section: 'rating' }),
      },
      {
        path: routePaths.events,
        lazy: () => import('@/pages/events'),
        handle: handle({ section: 'events' }),
      },
      { path: routePaths.event, lazy: () => import('@/pages/event'), handle: handle({ section: 'events' }) },
      { path: routePaths.race, lazy: () => import('@/pages/race'), handle: handle({ section: 'events' }) },
      {
        path: routePaths.adminRequests,
        lazy: () => import('@/pages/admin-requests'),
        handle: handle({ section: 'admin' }),
      },
      {
        path: routePaths.admin,
        lazy: () => import('@/pages/admin-requests'),
        handle: handle({ section: 'admin' }),
      },
      {
        path: routePaths.agentReview,
        lazy: () => import('@/pages/agent-review'),
        handle: handle({ section: 'agent' }),
      },
      { path: '*', element: <NotFound />, handle: handle({ section: 'search' }) },
    ],
  },
];

export const router = createBrowserRouter(routes);
