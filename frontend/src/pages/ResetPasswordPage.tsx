import { useState, type FormEvent } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { authApi } from '@/api/endpoints';
import { ApiError } from '@/api/client';
import { Icon } from '@/components/ui/Icon';

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const navigate = useNavigate();

  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

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
    setSubmitting(true);
    try {
      await authApi.passwordReset({ token, new_password: password });
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Ошибка при смене пароля. Возможно, ссылка устарела.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-gate-page">
      <div className="auth-card">
        <div className="auth-card__icon" aria-hidden="true">
          <Icon name="logo" />
        </div>
        <h1 className="auth-card__title">Новый пароль</h1>
        <p className="auth-card__subtitle">
          Задайте новый пароль для вашей учётной записи.
        </p>

        {success ? (
          <div className="auth-success" role="status">
            <p style={{ margin: '0 0 10px', fontWeight: 600 }}>Пароль успешно изменён!</p>
            <p style={{ margin: '0 0 16px' }}>Теперь вы можете войти в систему с новым паролем.</p>
            <button
              type="button"
              className="btn btn--primary btn--block"
              onClick={() => navigate('/')}
            >
              Перейти ко входу
            </button>
          </div>
        ) : !token ? (
          <div className="auth-error" role="alert">
            Неверная ссылка для сброса пароля. В URL отсутствует токен.
            <div style={{ marginTop: 12 }}>
              <Link to="/" className="btn btn--secondary btn--block">
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
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                disabled={submitting}
                autoFocus
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

            {error && <div className="auth-error" role="alert">{error}</div>}

            <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
              {submitting ? 'Сохранение…' : 'Установить пароль'}
            </button>

            <div className="auth-links" style={{ justifyContent: 'center' }}>
              <Link to="/" className="auth-link-btn">
                Вернуться ко входу
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
