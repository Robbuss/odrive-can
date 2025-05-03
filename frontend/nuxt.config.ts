export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  vite: {
    server: {
      proxy: {
        // Proxy any /api/... to http://127.0.0.1:8000/...
        '/api': {
          target: 'http://127.0.0.1:8000',  // use IPv4
          changeOrigin: true,
          rewrite: path => path.replace(/^\/api/, ''), 
          ws: true
        },
        // WebSocket proxy (if needed)
        '/ws': {
          target: 'ws://127.0.0.1:8000',
          ws: true,
          changeOrigin: true,
        }
      }
    }
  }
})
