import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_API_BASE_URL overrides the dev proxy in production builds.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // In dev the UI calls /api/... on its own origin and Vite forwards it to
      // the FastAPI server, so there is no CORS setup to get wrong.
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  // `npm run preview` serves the production build with the same proxy, so the
  // built app can be checked against a local backend before deploying.
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
