import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  server: {
    // Explicitly requested temporary HTTP testing; not a production server.
    host: '0.0.0.0', port: 8025, strictPort: true,
    // Vite accepts IP-literal Host headers by default; do not commit deployment addresses here.
    allowedHosts: ['localhost'],
    cors: false,
    fs: {
      strict: true,
      allow: [fileURLToPath(new URL('.', import.meta.url))],
      deny: ['**/.env', '**/.env.*', '**/*.{crt,pem,key}', '**/.git/**', '**/.runtime/**'],
    },
    headers: { 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer' },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8026', changeOrigin: true, timeout: 30000, proxyTimeout: 30000,
        configure(proxy) {
          proxy.on('proxyReq', (outgoing, incoming) => {
            // Backend trusts loopback proxy headers: never forward client-supplied IPs.
            outgoing.setHeader('X-Forwarded-For', incoming.socket.remoteAddress ?? 'unknown');
            outgoing.setHeader('X-Real-IP', incoming.socket.remoteAddress ?? 'unknown');
            outgoing.setHeader('X-Forwarded-Proto', 'http');
            outgoing.setHeader('X-Forwarded-Host', incoming.headers.host ?? '');
            outgoing.removeHeader('Forwarded');
            // Origin is deliberately preserved for backend CSRF/source validation.
          });
        },
      },
    },
  },
});
