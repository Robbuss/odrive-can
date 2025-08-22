export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  vite: {
    server: {
      proxy: {
        '^/api/(?!_nuxt_icon/)': {
          target: 'http://backend:8000', 
          changeOrigin: true,
          rewrite: p => p.replace(/^\/api/, ''),
          ws: true,                    
        },
      }
    }
  }
})
