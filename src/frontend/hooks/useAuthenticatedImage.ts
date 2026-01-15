/**
 * Hook for loading images via authenticated fetch (IMP-016)
 *
 * Replaces direct img src with authenticated fetch + createObjectURL pattern.
 * Handles loading states, errors, and cleanup of object URLs.
 */

import { useEffect, useState } from 'react';
import { apiFetch } from '../api/client';

interface UseAuthenticatedImageResult {
  objectUrl: string | null;
  loading: boolean;
  error: string | null;
}

/**
 * Hook to load image via authenticated fetch
 *
 * @param imagePath - API endpoint path for the image (e.g., '/runs/123/artifacts/file?path=...')
 * @returns Object with objectUrl, loading state, and error
 *
 * @example
 * const { objectUrl, loading, error } = useAuthenticatedImage(
 *   `/runs/${runId}/artifacts/file?path=${encodeURIComponent(path)}`
 * );
 */
export function useAuthenticatedImage(imagePath: string | null): UseAuthenticatedImageResult {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Reset state when path changes
    if (!imagePath) {
      setObjectUrl(null);
      setLoading(false);
      return;
    }

    let isMounted = true;
    let currentObjectUrl: string | null = null;

    const loadImage = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch image with authentication
        const response = await apiFetch(imagePath);

        if (!response.ok) {
          throw new Error(`Failed to load image: ${response.statusText}`);
        }

        // Get blob from response
        const blob = await response.blob();

        // Validate blob
        if (!blob.type.startsWith('image/')) {
          throw new Error('Invalid image format');
        }

        // Create object URL from blob
        currentObjectUrl = URL.createObjectURL(blob);

        // Only update state if component is still mounted
        if (isMounted) {
          setObjectUrl(currentObjectUrl);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load image');
          setObjectUrl(null);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadImage();

    // Cleanup function
    return () => {
      isMounted = false;
      // Revoke object URL to free memory
      if (currentObjectUrl) {
        URL.revokeObjectURL(currentObjectUrl);
      }
    };
  }, [imagePath]);

  return { objectUrl, loading, error };
}
