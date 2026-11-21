import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Providers } from './app/providers';

const root = document.getElementById('root');
if (!root) throw new Error('Отсутствует элемент root');
createRoot(root).render(
  <StrictMode>
    <Providers />
  </StrictMode>,
);
