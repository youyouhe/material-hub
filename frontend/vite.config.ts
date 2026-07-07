import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  server: {
    port: 3100,
    host: '0.0.0.0',
    allowedHosts: [
      'mcphubs.cc',
      '.mcphubs.cc',
      'senseflow.club',
      '.senseflow.club', // 允许所有子域名
    ],
    proxy: {
      '/api': {
        target: 'http://localhost:8201',
        changeOrigin: true,
        timeout: 600000,       // 10分钟超时，支持大文件上传
        proxyTimeout: 600000,
      },
      '/health': {
        target: 'http://localhost:8201',
        changeOrigin: true,
      },
    },
  },
  plugins: [react()],
});
