/**
 * Unified API client for frontend requests (IMP-009)
 *
 * Features:
 * - Automatic auth header injection (X-API-Key from localStorage or env)
 * - Dynamic base URL resolution from environment
 * - Consistent error handling
 * - TypeScript support
 */

/**
 * Configuration options for API client requests
 */
export interface ApiClientOptions extends RequestInit {
  /** Override default headers */
  headers?: Record<string, string>;
  /** Custom timeout in milliseconds */
  timeout?: number;
}

/**
 * Get API key from localStorage or environment variable
 * Priority: localStorage > environment variable > undefined
 */
function getApiKey(): string | undefined {
  // First try localStorage (for runtime override)
  if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
    const storedKey = localStorage.getItem('AUTOPACK_API_KEY');
    if (storedKey) {
      return storedKey;
    }
  }

  // Fall back to environment variable
  return import.meta.env.VITE_AUTOPACK_API_KEY;
}

/**
 * Get API base URL from environment or use default
 * Priority: environment variable > default (/api)
 */
function getApiBaseUrl(): string {
  return import.meta.env.VITE_AUTOPACK_API_BASE || '/api';
}

/**
 * Unified fetch wrapper for API requests
 *
 * Automatically:
 * - Injects X-API-Key header from localStorage or VITE_AUTOPACK_API_KEY
 * - Resolves full URL using VITE_AUTOPACK_API_BASE
 * - Applies timeout handling
 *
 * @param endpoint - Relative endpoint path (e.g., '/runs', '/runs/123/progress')
 * @param options - Fetch options (merged with auth headers)
 * @returns Promise<Response>
 *
 * @example
 * // Using the client
 * const response = await apiFetch('/runs?limit=20');
 * const data = await response.json();
 *
 * @example
 * // With custom headers
 * const response = await apiFetch('/runs', {
 *   method: 'POST',
 *   headers: { 'Content-Type': 'application/json' },
 *   body: JSON.stringify({ token_cap: 100000 })
 * });
 */
export async function apiFetch(
  endpoint: string,
  options?: ApiClientOptions
): Promise<Response> {
  const baseUrl = getApiBaseUrl();
  const apiKey = getApiKey();
  const timeout = options?.timeout || 30000; // Default 30s timeout

  // Build full URL
  const url = new URL(endpoint, baseUrl).toString();

  // Merge headers with auth
  const headers = {
    'Content-Type': 'application/json',
    ...(options?.headers || {}),
  };

  // Inject X-API-Key if available
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }

  // Create abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Utility to extract error message from API response
 * Handles various error response formats
 */
export async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json() as { detail?: string; message?: string; error?: string };
    return data.detail || data.message || data.error || response.statusText;
  } catch {
    // If response is not JSON, fall back to statusText
    return response.statusText;
  }
}
