import { transferableAbortController } from 'node:util';
import { cleanup } from '@testing-library/react';
import { afterEach, afterAll, vi } from 'vitest';
import { server } from './server';

vi.stubGlobal(
  'AbortController',
  class {
    constructor() {
      return transferableAbortController();
    }
  },
);
server.listen({ onUnhandledRequest: 'error' });
afterEach(() => {
  cleanup();
  server.resetHandlers();
  localStorage.clear();
});
afterAll(() => server.close());
