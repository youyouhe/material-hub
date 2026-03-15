/**
 * Authentication service for MaterialHub frontend.
 * Manages authentication tokens in localStorage.
 */

const TOKEN_KEY = 'materialhub_auth_token';
const USER_KEY = 'materialhub_user';

/**
 * Get the current authentication token from localStorage.
 */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Save an authentication token to localStorage.
 */
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Clear the authentication token from localStorage.
 */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function setUser(user: { id: number; username: string; role: string }): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getUser(): { id: number; username: string; role: string } | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

/**
 * Check if the user is authenticated (has a token).
 * Note: This only checks if a token exists, not if it's valid.
 * Use the /api/auth/check endpoint to verify token validity.
 */
export function isAuthenticated(): boolean {
  return getToken() !== null;
}
