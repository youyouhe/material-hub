/**
 * Authentication service for MaterialHub frontend.
 * Manages authentication tokens in localStorage.
 */

const TOKEN_KEY = 'materialhub_auth_token';

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
}

/**
 * Check if the user is authenticated (has a token).
 * Note: This only checks if a token exists, not if it's valid.
 * Use the /api/auth/check endpoint to verify token validity.
 */
export function isAuthenticated(): boolean {
  return getToken() !== null;
}
