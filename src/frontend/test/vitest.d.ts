/**
 * TypeScript definitions for Vitest + jest-dom matchers
 *
 * Extends Vitest's Assertion interface with jest-dom custom matchers
 */
import '@testing-library/jest-dom';
import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers';

declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  interface Assertion<T = any> extends TestingLibraryMatchers<typeof expect.stringContaining, T> {}
}
