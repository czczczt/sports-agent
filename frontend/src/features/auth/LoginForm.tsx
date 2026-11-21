import { ApiError } from '@/shared/api';
import { useAuth } from '@/shared/session';
import { useState, type FormEvent } from 'react';

import type { AuthFormProps } from './AuthForm';
export function LoginForm({ switchMode }: AuthFormProps): React.JSX.Element {
  const { login } = useAuth();
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleLoginSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!loginUsername.trim() || !loginPassword) {
      setError('Заполните логин и пароль');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await login(loginUsername.trim(), loginPassword);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Ошибка при входе');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleLoginSubmit} className="modal-form">
      <label className="field">
        <span>Логин или Email</span>
        <input
          type="text"
          name="username"
          className="input"
          value={loginUsername}
          onChange={(e) => setLoginUsername(e.target.value)}
          autoComplete="username"
          disabled={submitting}
        />
      </label>

      <label className="field">
        <span>Пароль</span>
        <input
          type="password"
          name="password"
          className="input"
          value={loginPassword}
          onChange={(e) => setLoginPassword(e.target.value)}
          autoComplete="current-password"
          disabled={submitting}
        />
      </label>

      {error && (
        <div className="auth-error" role="alert">
          {error}
        </div>
      )}

      <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
        {submitting ? 'Вход…' : 'Войти'}
      </button>

      <div className="auth-links">
        <button type="button" className="auth-link-btn" onClick={() => switchMode('reset')}>
          Забыли пароль?
        </button>
        <button type="button" className="auth-link-btn" onClick={() => switchMode('register')}>
          Подать заявку на доступ
        </button>
      </div>
    </form>
  );
}
