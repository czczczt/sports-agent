import '@fontsource/golos-text/400.css';
import '@fontsource/golos-text/500.css';
import '@fontsource/golos-text/600.css';
import '@fontsource/unbounded/600.css';
import '@fontsource/unbounded/700.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './styles/base.css';

import { AuthProvider } from '@/shared/session';
import { ThemeProvider } from '@/shared/theme';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';

import { ApiError } from '@/shared/api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      gcTime: 300000,
      retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status >= 500),
    },
    mutations: { retry: false },
  },
});

export function Providers(): React.JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
