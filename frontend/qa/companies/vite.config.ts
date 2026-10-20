// Opt-in QA server only. Production vite.config.ts and main.tsx are unchanged.
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  envDir: false,
  plugins: [react(), tailwindcss(), {
    name: 'explicit-test-adapters-banner',
    transformIndexHtml: html => html.replace('<body>', '<body><div style="padding:8px;background:#ffedab;color:#222;text-align:center">LOCAL QA — test Auth / MemoryStore / Gemini / Homeportal / ADATA MockTransport. No live Firebase or AI.</div>'),
  }],
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('') },
  resolve: { alias: [
    { find: /^@\/lib\/firebase$/, replacement: fileURLToPath(new URL('../release/firebase.ts', import.meta.url)) },
    { find: /^firebase\/auth$/, replacement: fileURLToPath(new URL('../release/firebase-auth.ts', import.meta.url)) },
    { find: '@', replacement: fileURLToPath(new URL('../../src', import.meta.url)) },
  ] },
  server: { host: '127.0.0.1', port: 5182, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8012' } },
})
