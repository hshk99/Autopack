/**
 * Vitest global test setup
 *
 * Configures testing-library matchers and global test environment
 */
import { expect } from 'vitest';
import * as matchers from '@testing-library/jest-dom/matchers';

// Extend Vitest's expect with jest-dom matchers
expect.extend(matchers);
