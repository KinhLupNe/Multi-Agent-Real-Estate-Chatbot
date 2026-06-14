import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/chat': 'http://127.0.0.1:8000',
      '/dashboard': 'http://127.0.0.1:8000',
      '/get_price': 'http://127.0.0.1:8000',
      '/get_area': 'http://127.0.0.1:8000',
      '/set_active_province': 'http://127.0.0.1:8000',
    }
  }
})
