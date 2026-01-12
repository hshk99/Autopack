/**
 * Basic test to verify test harness works
 */
import { describe, it, expect } from 'vitest';

describe('Basic test suite', () => {
  it('should run a simple test', () => {
    expect(1 + 1).toBe(2);
  });

  it('should handle string operations', () => {
    expect('hello'.toUpperCase()).toBe('HELLO');
  });
});
