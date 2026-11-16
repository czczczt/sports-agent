import { useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Icon } from '@/components/ui/Icon';
import { ApiError } from '@/api/client';

export function AuthForm({ autoFocus = true }: { autoFocus?: boolean }) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Заполните логин и пароль');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
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
    <form onSubmit={handleSubmit} className="modal-form">
      <label className="field">
        <span>Логин</span>
        <input
          type="text"
          name="username"
          className="input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus={autoFocus}
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
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          disabled={submitting}
        />
      </label>

      {error && (
        <div className="auth-error" role="alert">
          {error}
        </div>
      )}

      <button
        type="submit"
        className="btn btn--primary btn--block"
        disabled={submitting}
      >
        {submitting ? 'Вход…' : 'Войти'}
      </button>
    </form>
  );
}

/** Карточка входа для неавторизованных пользователей (закрытый доступ). */
export function AuthCard() {
  return (
    <div className="auth-card">
      <div className="auth-card__icon" aria-hidden="true">
        <Icon name="logo" />
      </div>
      <h1 className="auth-card__title">Вход в систему</h1>
      <p className="auth-card__subtitle">
        Внутренний сервис платформы рейтинга спортсменов. Для просмотра данных войдите в систему.
      </p>
      <AuthForm autoFocus={true} />
    </div>
  );
}

/** Всплывающее модальное окно авторизации. */
export function AuthModal() {
  const { isAuthModalOpen, closeAuthModal } = useAuth();

  useEffect(() => {
    if (!isAuthModalOpen) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeAuthModal();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isAuthModalOpen, closeAuthModal]);

  if (!isAuthModalOpen) return null;

  return (
    <div
      className="modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeAuthModal();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
    >
      <div className="modal-card">
        <button
          type="button"
          className="modal-close"
          onClick={closeAuthModal}
          aria-label="Закрыть окно авторизации"
        >
          <Icon name="close" />
        </button>

        <h2 id="auth-modal-title" className="modal-title">Вход в систему</h2>
        <AuthForm autoFocus={true} />
      </div>
    </div>
  );
}
