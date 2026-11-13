import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { ThemeProvider } from '@/theme/ThemeProvider';
import { router } from '@/routes';
import 'air-datepicker/air-datepicker.css';
import '@/styles/theme.css';
import '@/styles/app.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <RouterProvider router={router} />
    </ThemeProvider>
  </StrictMode>,
);
