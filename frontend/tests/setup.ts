import { transferableAbortController } from 'node:util';
import { cleanup } from '@testing-library/react';
import { afterEach, afterAll, vi } from 'vitest';
import { server } from './server';

const storageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
    length: 0,
    key: () => null,
  };
})();
Object.defineProperty(globalThis, 'localStorage', {
  value: storageMock,
  writable: true,
  configurable: true,
});

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
