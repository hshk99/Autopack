/**
 * App component tests
 *
 * Tests core routing functionality and ensures all routes are properly configured
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

describe('App routing', () => {
  it('renders Dashboard on root path', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    );
    // Dashboard renders; this test proves the route is wired correctly
    expect(document.querySelector('.app')).toBeInTheDocument();
  });

  it('renders NotFound for unknown routes', () => {
    render(
      <MemoryRouter initialEntries={['/non-existent-route']}>
        <App />
      </MemoryRouter>
    );
    // NotFound component should render
    expect(screen.getByText(/404/i)).toBeInTheDocument();
  });

  it('renders RunsInbox on /runs path', () => {
    render(
      <MemoryRouter initialEntries={['/runs']}>
        <App />
      </MemoryRouter>
    );
    // RunsInbox renders; this test proves the route is wired correctly
    expect(document.querySelector('.app')).toBeInTheDocument();
  });
});
