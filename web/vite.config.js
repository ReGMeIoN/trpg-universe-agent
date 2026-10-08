import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式: 前端 5173, API 反向代理到本地面板后端(8765)
// 生产模式: npm run build -> web/dist, 由 FastAPI 直接托管
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
