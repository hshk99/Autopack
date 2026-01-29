/**
 * Vitest global test setup
 *
 * Configures testing-library matchers and global test environment
 *
 * Windows/Node 18+ Compatibility (IMP-FE-001):
 * - Uses @testing-library/jest-dom for DOM matchers
 * - Cleanup is handled automatically by @testing-library/react in modern versions
 */
import '@testing-library/jest-dom';
