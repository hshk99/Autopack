/**
 * NotFound component tests
 *
 * Tests the 404 page rendering and navigation link
 * Note: Uses vitest globals mode (IMP-FE-001)
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NotFound from './NotFound';

describe('NotFound component', () => {
  it('renders 404 message', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    expect(screen.getByText(/404/i)).toBeInTheDocument();
  });

  it('renders link back to home', () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    );
    const homeLink = screen.getByRole('link', { name: /home|back|dashboard/i });
    expect(homeLink).toBeInTheDocument();
    expect(homeLink).toHaveAttribute('href', '/');
  });
});
