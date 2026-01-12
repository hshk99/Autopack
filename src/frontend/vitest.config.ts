/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Vitest configuration for Autopack frontend tests
 *
 * Uses same path aliases as vite.config.ts for consistency
 * Configured with jsdom environment for React component testing
 */
export default defineConfig({
  plugins: [react()],

  test: {
    environment: 'jsdom',
    // setupFiles: ['./src/frontend/test/setup.ts'],
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/frontend/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/mockData',
        'dist/',
      ],
    },
  },

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
});
