import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // The dashboard imports these controls on first paint. Leave feature-only
        // packages (notably Vue Flow) to Rollup's dynamic import boundaries.
        manualChunks(id) {
          if (/\/node_modules\/(?:vue|vue-router|vue-i18n|@vue|@intlify)\//.test(id)) return 'vue-runtime'
          if (/\/naive-ui\/es\/(?:input|select|form|menu|tabs|dropdown|modal|dialog)\/src\//.test(id)) return 'ui-controls'
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/aivuda_os/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
