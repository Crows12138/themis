import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies the kernel API to the FastAPI backend
// (`python -m themis.web`, default :8000) so there is no CORS in dev and
// the same relative `/api/*` paths work in the production build that
// FastAPI serves from `frontend/dist`.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Emitted into the package so FastAPI can serve the built product.
    outDir: 'dist',
  },
})
