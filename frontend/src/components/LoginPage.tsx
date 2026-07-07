import { useState } from 'react';
import { loginV2 } from '../services/api-v2';

interface LoginPageProps {
  onLogin: (token: string, user?: { id: number; username: string; role: string }) => void;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await loginV2(username, password);
      onLogin(response.token, response.user as { id: number; username: string; role: string });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-cp-bg flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <h1 className="text-4xl font-orbitron font-bold text-cp-purple glow-purple">MaterialHub</h1>
        <div className="neon-divider-purple w-48 mx-auto mt-4"></div>
        <h2 className="mt-6 text-xl font-exo text-cp-muted">
          登录到您的账户
        </h2>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="cp-card rounded-lg py-8 px-4 sm:px-10">
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-cp-muted">
                用户名
              </label>
              <div className="mt-1">
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="cp-input block w-full px-3 py-2 rounded-md text-sm"
                  disabled={loading}
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-cp-muted">
                密码
              </label>
              <div className="mt-1">
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="cp-input block w-full px-3 py-2 rounded-md text-sm"
                  disabled={loading}
                />
              </div>
            </div>

            {error && (
              <div className="rounded-md bg-cp-rose/10 border border-cp-rose/30 p-4">
                <p className="text-sm font-medium text-cp-rose">{error}</p>
              </div>
            )}

            <div>
              <button
                type="submit"
                disabled={loading}
                className="cp-btn-primary w-full flex justify-center py-2.5 px-4 rounded-md"
              >
                {loading ? '登录中...' : '登录'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
