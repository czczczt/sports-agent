import { ApiError } from '@/shared/api';
import { authApi } from '@/shared/session';
import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import styles from './PasswordRequestForm.module.css';

import type { AuthFormProps } from './AuthForm';
export function PasswordRequestForm({ switchMode }: AuthFormProps): React.JSX.Element {
  const resetRequest = useMutation({ mutationFn: authApi.passwordResetRequest });

  const [resetEmail, setResetEmail] = useState('');

  const [error, setError] = useState<string | null>(null);
  const successMsg = resetRequest.data?.message;
  const submitting = resetRequest.isPending;

  const handleResetSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!resetEmail.trim()) {
      setError('Укажите ваш email');
      return;
    }

    setError(null);
    try {
      await resetRequest.mutateAsync({ email: resetEmail.trim() });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Ошибка при запросе сброса пароля');
      }
    }
  };

  return (
    <form onSubmit={handleResetSubmit} className="modal-form">
      <p className={['auth-card__subtitle', styles.instructions].join(' ')}>
        Введите email, указанный при регистрации. Мы отправим ссылку для установки нового пароля.
      </p>

      {successMsg ? (
        <div className="auth-success" role="status">
          {successMsg}
          <div className={styles.successActions}>
            <button
              type="button"
              className="btn btn--secondary btn--block"
              onClick={() => switchMode('login')}
            >
              Вернуться ко входу
            </button>
          </div>
        </div>
      ) : (
        <>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              name="email"
              className="input"
              value={resetEmail}
              onChange={(e) => setResetEmail(e.target.value)}
              autoComplete="email"
              required
              disabled={submitting}
            />
          </label>

          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}

          <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
            {submitting ? 'Отправка…' : 'Отправить ссылку'}
          </button>

          <div className={['auth-links', styles.links].join(' ')}>
            <button type="button" className="auth-link-btn" onClick={() => switchMode('login')}>
              Вернуться ко входу
            </button>
          </div>
        </>
      )}
    </form>
  );
}
