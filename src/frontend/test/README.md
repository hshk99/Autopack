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

## Known Issues

### Test Execution Error (Windows/Node 18/Vitest)

**Symptom**:
```
Error: No test suite found in file C:/dev/Autopack/src/frontend/App.test.tsx
```

**Context**:
- Affects all test files (even minimal JS tests with no imports)
- Persists across Vitest versions (0.34.x and 1.6.x)
- Not related to setup file (fails even with setup disabled)
- Not related to TypeScript (fails with plain JS files)
- Environment: Windows 11, Node 18.20.4, npm 10.7.0

**Investigation**:
- Vitest can find and load test files (shown in "collecting..." phase)
- Transform phase completes successfully
- Setup phase completes (when enabled)
- Collect phase shows 0 tests despite valid describe/it blocks
- Error suggests Vitest cannot parse the describe/it/expect calls

**Possible Causes**:
1. Windows path handling issue in Vitest
2. Node 18 + Vitest compatibility (ESM/CJS interop)
3. vite.config.ts/vitest.config.ts conflict
4. Missing/incompatible peer dependency

**Next Steps**:
1. Try on Linux/macOS to isolate Windows-specific issue
2. Try Node 20 LTS
3. Try simpler test config (no plugins, no aliases)
4. Check for conflicting vite/vitest versions
5. Review Vitest GitHub issues for similar reports

**Workaround**:
- Infrastructure is complete and test files are valid
- Tests can be reviewed manually
- Once execution issue is resolved, tests will run in CI

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
