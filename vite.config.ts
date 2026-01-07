import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Vite configuration for Autopack frontend
 * 
 * Features:
 * - React with Fast Refresh
 * - TypeScript support
 * - Path aliases for clean imports
 * - Proxy to backend API during development
 * - Optimized production builds
 */
export default defineConfig({
  plugins: [react()],
  
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src/frontend'),
      '@components': path.resolve(__dirname, './src/frontend/components'),
      '@pages': path.resolve(__dirname, './src/frontend/pages'),
      '@hooks': path.resolve(__dirname, './src/frontend/hooks'),
      '@utils': path.resolve(__dirname, './src/frontend/utils'),
      '@types': path.resolve(__dirname, './src/frontend/types'),
    },
  },

  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
});
