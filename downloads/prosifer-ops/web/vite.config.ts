import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, /api va a la API local (docker compose la publica en 127.0.0.1:8110).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8110' } },
})
