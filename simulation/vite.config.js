import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const bridgeUrl = env.VITE_SISP_WS_URL || `ws://localhost:${env.SISP_PORT || 3001}`;

  return {
    plugins: [react()],
    server: {
      port: 5173,
      open: true,
      proxy: {
        // Forward /ws to the C++ bridge WebSocket server.
        '/ws': {
          target: bridgeUrl,
          ws: true,
          rewrite: (path) => path.replace(/^\/ws/, ''),
        },
      },
    },
  };
});
