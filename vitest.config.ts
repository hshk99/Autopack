/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Vitest configuration for Autopack frontend tests
 *
 * Root-level config for better Windows/Node 18 compatibility (IMP-FE-001)
 * Configured with jsdom environment for React component testing
 */
export default defineConfig({
  plugins: [react()],

  test: {
    environment: 'jsdom',
    // Enable globals mode - vitest injects describe/it/expect globally
    // This avoids ESM import issues on Windows/Node 18
    globals: true,
    // Setup file loads jest-dom matchers (toBeInTheDocument, etc.)
    setupFiles: ['./src/frontend/test/setup.ts'],
    // Include test files from src/frontend
    include: ['src/frontend/**/*.test.{ts,tsx}'],
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
