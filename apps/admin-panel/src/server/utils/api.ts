import { useAppSession } from '../session';

export function getApiBaseUrl(): string {
  if (typeof process !== 'undefined' && process.env?.VITE_API_BASE_URL) {
    return process.env.VITE_API_BASE_URL;
  }
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  return 'http://localhost:3080';
}

/** Server-to-server API URL. Falls back to getApiBaseUrl() if API_SERVER_URL is not set. */
export function getServerApiUrl(): string {
  if (typeof process !== 'undefined' && process.env?.API_SERVER_URL) {
    return process.env.API_SERVER_URL;
  }
  return getApiBaseUrl();
}

/**
 * Make an authenticated request to the LibreChat API.
 * Reads the JWT token from the admin session and sets the Authorization header.
 *
 * @throws {Error} If no session token is available
 */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const session = await useAppSession();
  const token = session.data.token;
  if (!token) {
    throw new Error('No admin session token available');
  }

  const url = `${getServerApiUrl()}${path}`;
  return fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
}

/**
 * Extract an error message from a failed API response and throw.
 * Handles both `{ error }` and `{ message }` response shapes.
 */
export async function extractApiError(response: Response, fallback: string): Promise<never> {
  const body = await response.json().catch(() => ({}));
  const message =
    (body as { error?: string }).error ??
    (body as { message?: string }).message ??
    `${fallback}: ${response.status}`;
  throw new Error(message);
}
