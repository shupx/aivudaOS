import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import legacy from '@vitejs/plugin-legacy'

export default defineConfig({
  base: '/_aivuda_h16/',
  plugins: [
    vue(),
    {
      name: 'h16-webview-entry',
      transformIndexHtml: {
        order: 'pre',
        handler: () => [{
          tag: 'script',
          attrs: { type: 'module', src: '/src/h16-panel.js' },
          injectTo: 'body-prepend',
        }],
      },
    },
    legacy({
      targets: ['Chrome 52'],

      additionalLegacyPolyfills: ['resize-observer-polyfill/dist/ResizeObserver.global.js'],
    }),
  ],
  build: { outDir: '../../../android/build/panel', emptyOutDir: true },
})
