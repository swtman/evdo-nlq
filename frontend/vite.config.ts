import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/query': 'http://localhost:8000',
      '/providers': 'http://localhost:8000',
    },
  },
})
