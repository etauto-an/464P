import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy API requests to the FastAPI backend running on port 8000.
    // This avoids CORS issues during local development and keeps fetch()
    // calls in the frontend path-relative (e.g. fetch('/inventory')).
    proxy: {
      '/inventory': 'http://localhost:8000',
      '/events': 'http://localhost:8000',
      '/sync': 'http://localhost:8000',
    },
  },
})
