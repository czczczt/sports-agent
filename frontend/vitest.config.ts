import { mergeConfig, defineConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      setupFiles: ['./tests/setup.ts'],
      environmentOptions: { jsdom: { url: 'http://localhost:5173' } },
    },
  }),
);
