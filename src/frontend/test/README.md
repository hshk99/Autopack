# Frontend Test Harness

**Status**: Infrastructure complete, execution troubleshooting in progress
**Last Updated**: 2026-01-12

## Overview

The frontend test harness uses Vitest + React Testing Library + jsdom for component and unit testing.

## Quick Start

```bash
# Run all tests
npm test

# Watch mode (re-run on file changes)
npm run test:watch

# UI mode (interactive test browser)
npm run test:ui

# Coverage report
npm run test:coverage
```

## Configuration

- **vitest.config.ts**: Test framework configuration
  - Environment: jsdom (browser simulation)
  - Setup file: `src/frontend/test/setup.ts`
  - Path aliases match vite.config.ts
  - Coverage provider: v8

- **src/frontend/test/setup.ts**: Test environment setup
  - Extends Vitest `expect` with jest-dom matchers (`toBeInTheDocument`, etc.)
  - Auto-cleanup after each test

## Test Files

### Example Tests (Infrastructure Validation)

1. **App.test.tsx** - Routing tests
   - Dashboard route (`/`)
   - NotFound route (`*`)
   - RunsInbox route (`/runs`)

2. **pages/NotFound.test.tsx** - 404 page tests
   - Renders 404 message
   - Renders link back to home

3. **components/MultiFileUpload.test.tsx** - Component tests
   - Renders drop zone
   - Displays file size/count limits
   - Validates file size
   - Respects maxFiles limit
   - Handles file selection

4. **test/basic.test.ts** - Basic harness validation
   - Simple describe/it/expect test

## Resolved Issues

### Test Execution Error (Windows/Node 18/Vitest) - FIXED in IMP-FE-001

**Original Symptom**:
```
Error: No test suite found in file C:/dev/Autopack/src/frontend/App.test.tsx
```

**Root Cause**:
The issue was caused by ESM module resolution problems with explicit vitest imports
on Windows + Node 18. Tests were found but `describe`/`it`/`expect` blocks weren't
being recognized when imported from 'vitest'.

**Solution (IMP-FE-001)**:
1. Upgraded Vitest from 0.34.x to 1.6.x for better Windows support
2. Moved vitest.config.ts to project root
3. Enabled `globals: true` mode - vitest injects test functions globally
4. Updated test files to use global describe/it/expect (no imports)
5. Fixed jest-dom setup with `import '@testing-library/jest-dom'`

**Key Config Changes**:
```typescript
// vitest.config.ts (at project root)
export default defineConfig({
  test: {
    globals: true,  // Key fix - avoids ESM import issues
    environment: 'jsdom',
    setupFiles: ['./src/frontend/test/setup.ts'],
    include: ['src/frontend/**/*.test.{ts,tsx}'],
  },
});
```

**Test Status**: All infrastructure tests passing (10/13, 3 skipped for component fixes)

## Writing Tests

### Component Test Template

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MyComponent from './MyComponent';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(
      <MemoryRouter>
        <MyComponent />
      </MemoryRouter>
    );
    expect(screen.getByText(/expected text/i)).toBeInTheDocument();
  });
});
```

### User Interaction Test

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MyForm from './MyForm';

describe('MyForm interactions', () => {
  it('handles button click', async () => {
    const user = userEvent.setup();
    render(<MyForm />);

    const button = screen.getByRole('button', { name: /submit/i });
    await user.click(button);

    expect(screen.getByText(/success/i)).toBeInTheDocument();
  });
});
```

### Mocking API Calls

```typescript
import { describe, it, expect, vi } from 'vitest';

describe('API integration', () => {
  it('fetches data', async () => {
    // Mock fetch
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      } as Response)
    );

    // Test component that uses fetch
    // ...
  });
});
```

## Best Practices

1. **Test user behavior, not implementation**
   - Query by role, label, text (not by class/ID)
   - Simulate real user interactions

2. **Keep tests focused**
   - One assertion concept per test
   - Use descriptive test names

3. **Use data-testid sparingly**
   - Prefer semantic queries (getByRole, getByLabelText)
   - Only use data-testid when semantic queries aren't possible

4. **Mock external dependencies**
   - API calls
   - Browser APIs (localStorage, etc.)
   - Third-party libraries

5. **Avoid testing library internals**
   - Don't test React state directly
   - Test what the user sees/does

## CI Integration (Future)

Once test execution is working:

```yaml
# .github/workflows/frontend-tests.yml
name: Frontend Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - run: npm install
      - run: npm test
      - run: npm run test:coverage
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage/coverage-final.json
```

## References

- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- [jest-dom Matchers](https://github.com/testing-library/jest-dom)
- [Testing Library Queries](https://testing-library.com/docs/queries/about)
