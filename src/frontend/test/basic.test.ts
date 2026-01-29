/**
 * Basic test to verify test harness works
 *
 * Note: Uses vitest globals mode (IMP-FE-001) - no explicit imports needed
 */

describe('Basic test suite', () => {
  it('should run a simple test', () => {
    expect(1 + 1).toBe(2);
  });

  it('should handle string operations', () => {
    expect('hello'.toUpperCase()).toBe('HELLO');
  });
});
