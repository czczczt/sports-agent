import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// Бэкенд FastAPI. В dev Vite проксирует к нему все запросы /api/...
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND_URL, changeOrigin: true },
      '/docs': { target: BACKEND_URL, changeOrigin: true },
      '/openapi.json': { target: BACKEND_URL, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Chart.js и Air Datepicker — в отдельные чанки: меняются редко и кэшируются браузером.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['chart.js'],
          datepicker: ['air-datepicker'],
        },
      },
    },
  },
});
