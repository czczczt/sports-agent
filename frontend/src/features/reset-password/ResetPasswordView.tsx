import { ApiError } from '@/shared/api';
import { paths } from '@/shared/config';
import { authApi } from '@/shared/session';
import { Icon } from '@/shared/ui';
import { useMutation } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import styles from './ResetPasswordView.module.css';

export function ResetPasswordView(): React.JSX.Element {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const reset = useMutation({ mutationFn: authApi.passwordReset });
  const passwordInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (token && document.activeElement === document.body)
      passwordInput.current?.focus({ preventScroll: true });
  }, [token]);
  const navigate = useNavigate();

  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const success = reset.isSuccess;
  const submitting = reset.isPending;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError('В ссылке отсутствует токен сброса пароля.');
      return;
    }
    if (password.length < 6) {
      setError('Пароль должен содержать не менее 6 символов.');
      return;
    }
    if (password !== passwordConfirm) {
      setError('Пароли не совпадают.');
      return;
    }

    setError(null);
    try {
      await reset.mutateAsync({ token, new_password: password });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Ошибка при смене пароля. Возможно, ссылка устарела.');
      }
    }
  };

  return (
    <div className="auth-gate-page">
      <div className="auth-card">
        <div className="auth-card__icon" aria-hidden="true">
          <Icon name="logo" />
        </div>
        <h1 className="auth-card__title">Новый пароль</h1>
        <p className="auth-card__subtitle">Задайте новый пароль для вашей учётной записи.</p>

        {success ? (
          <div className="auth-success" role="status">
            <p className={styles.successTitle}>Пароль успешно изменён!</p>
            <p className={styles.message}>Теперь вы можете войти в систему с новым паролем.</p>
            <button
              type="button"
              className="btn btn--primary btn--block"
              onClick={() => navigate(paths.search)}
            >
              Перейти ко входу
            </button>
          </div>
        ) : !token ? (
          <div className="auth-error" role="alert">
            Неверная ссылка для сброса пароля. В URL отсутствует токен.
            <div className={styles.actions}>
              <Link to={paths.search} className="btn btn--secondary btn--block">
                На главную
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="modal-form">
            <label className="field">
              <span>Новый пароль</span>
              <input
                type="password"
                name="password"
                ref={passwordInput}
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                disabled={submitting}
              />
            </label>

            <label className="field">
              <span>Повторите пароль</span>
              <input
                type="password"
                name="passwordConfirm"
                className="input"
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                autoComplete="new-password"
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
              {submitting ? 'Сохранение…' : 'Установить пароль'}
            </button>

            <div className={['auth-links', styles.links].join(' ')}>
              <Link to={paths.search} className="auth-link-btn">
                Вернуться ко входу
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
