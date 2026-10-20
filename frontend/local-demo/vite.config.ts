import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  envDir: false,
  plugins: [react(), tailwindcss(), {
    name: 'local-demo-disclosure',
    transformIndexHtml: html => html.replace('<body>', `<body><aside style="padding:12px 20px;background:#fff1c2;color:#243c40;font:15px/1.5 system-ui;text-align:center;border-bottom:1px solid #d4b356">
      <strong>Локальная демонстрация.</strong> Данные вымышлены; Gemini и сбор источников заменены учебными примерами.
      Вход: <strong>analyst@example.test</strong> / <strong>demo-demo</strong>. Изменения сохраняются только на этом компьютере.
    </aside>`),
  }],
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('') },
  resolve: { alias: [
    { find: /^@\/lib\/firebase$/, replacement: fileURLToPath(new URL('./firebase.ts', import.meta.url)) },
    { find: /^firebase\/auth$/, replacement: fileURLToPath(new URL('./firebase-auth.ts', import.meta.url)) },
    { find: '@', replacement: fileURLToPath(new URL('../src', import.meta.url)) },
  ] },
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: { '/api': process.env.SAQ_DEMO_PROXY || 'http://127.0.0.1:8000' },
    headers: { 'Content-Security-Policy': "connect-src 'self' ws://localhost:5173 ws://127.0.0.1:5173; img-src 'self' data: blob:; font-src 'self' data:" },
  },
})
