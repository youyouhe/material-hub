import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  server: {
    port: 3100,
    host: '0.0.0.0',
    allowedHosts: [
      'mcphubs.cc',
      '.mcphubs.cc', // 允许所有子域名
    ],
    proxy: {
      '/api': {
        target: 'http://localhost:8201',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8201',
        changeOrigin: true,
      },
    },
  },
  plugins: [react()],
});
