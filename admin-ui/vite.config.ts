import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  build: {
    outDir: '../admin-static',
    emptyOutDir: true,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/admin/api': 'http://127.0.0.1:9996',
      '/v1': 'http://127.0.0.1:9996',
      '/health': 'http://127.0.0.1:9996',
    },
  },
});
