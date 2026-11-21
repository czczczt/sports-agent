import { useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/context/AuthContext';
import { authApi } from '@/api/endpoints';
import { Icon } from '@/components/ui/Icon';
import { ApiError } from '@/api/client';

export type AuthMode = 'login' | 'register' | 'reset';

export function AuthForm({
  autoFocus = true,
  initialMode = 'login',
  onModeChange,
}: {
  autoFocus?: boolean;
  initialMode?: AuthMode;
  onModeChange?: (mode: AuthMode) => void;
}) {
  const { login } = useAuth();
  const [mode, setMode] = useState<AuthMode>(initialMode);

  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regLastName, setRegLastName] = useState('');
  const [regFirstName, setRegFirstName] = useState('');
  const [regMiddleName, setRegMiddleName] = useState('');
  const [regCity, setRegCity] = useState('');
  const [regBirthDate, setRegBirthDate] = useState('');
  const [regConsent, setRegConsent] = useState(false);

  const [resetEmail, setResetEmail] = useState('');

  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const switchMode = (newMode: AuthMode) => {
    setMode(newMode);
    setError(null);
    setSuccessMsg(null);
    onModeChange?.(newMode);
  };

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

  const handleRegisterSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!regUsername.trim() || !regEmail.trim() || !regPassword || !regLastName.trim() || !regFirstName.trim()) {
      setError('Заполните все обязательные поля');
      return;
    }
    if (!regConsent) {
      setError('Необходимо согласие на обработку персональных данных (ФЗ-152)');
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const res = await authApi.register({
        username: regUsername.trim(),
        email: regEmail.trim(),
        password: regPassword,
        last_name: regLastName.trim(),
        first_name: regFirstName.trim(),
        middle_name: regMiddleName.trim() || null,
        city: regCity.trim() || null,
        birth_date: regBirthDate || null,
        consent: regConsent,
      });
      setSuccessMsg(res.message || 'Заявка на доступ успешно подана и ожидает подтверждения.');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Ошибка при отправке заявки');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleResetSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!resetEmail.trim()) {
      setError('Укажите ваш email');
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const res = await authApi.passwordResetRequest({ email: resetEmail.trim() });
      setSuccessMsg(res.message);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Ошибка при запросе сброса пароля');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (mode === 'reset') {
    return (
      <form onSubmit={handleResetSubmit} className="modal-form">
        <p className="auth-card__subtitle" style={{ margin: '0 0 12px', fontSize: 13 }}>
          Введите email, указанный при регистрации. Мы отправим ссылку для установки нового пароля.
        </p>

        {successMsg ? (
          <div className="auth-success" role="status">
            {successMsg}
            <div style={{ marginTop: 12 }}>
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
                autoFocus={autoFocus}
                autoComplete="email"
                required
                disabled={submitting}
              />
            </label>

            {error && <div className="auth-error" role="alert">{error}</div>}

            <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
              {submitting ? 'Отправка…' : 'Отправить ссылку'}
            </button>

            <div className="auth-links" style={{ justifyContent: 'center' }}>
              <button type="button" className="auth-link-btn" onClick={() => switchMode('login')}>
                Вернуться ко входу
              </button>
            </div>
          </>
        )}
      </form>
    );
  }

  if (mode === 'register') {
    return (
      <form onSubmit={handleRegisterSubmit} className="modal-form">
        {successMsg ? (
          <div className="auth-success" role="status">
            <p style={{ margin: '0 0 10px', fontWeight: 600 }}>Заявка принята!</p>
            <p style={{ margin: 0 }}>{successMsg}</p>
            <div style={{ marginTop: 14 }}>
              <button
                type="button"
                className="btn btn--primary btn--block"
                onClick={() => switchMode('login')}
              >
                Вернуться ко входу
              </button>
            </div>
          </div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label className="field">
                <span>Фамилия *</span>
                <input
                  type="text"
                  name="lastName"
                  className="input"
                  value={regLastName}
                  onChange={(e) => setRegLastName(e.target.value)}
                  autoFocus={autoFocus}
                  required
                  disabled={submitting}
                />
              </label>

              <label className="field">
                <span>Имя *</span>
                <input
                  type="text"
                  name="firstName"
                  className="input"
                  value={regFirstName}
                  onChange={(e) => setRegFirstName(e.target.value)}
                  required
                  disabled={submitting}
                />
              </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label className="field">
                <span>Отчество</span>
                <input
                  type="text"
                  name="middleName"
                  className="input"
                  value={regMiddleName}
                  onChange={(e) => setRegMiddleName(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <label className="field">
                <span>Город</span>
                <input
                  type="text"
                  name="city"
                  className="input"
                  value={regCity}
                  onChange={(e) => setRegCity(e.target.value)}
                  disabled={submitting}
                />
              </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label className="field">
                <span>Дата рождения</span>
                <input
                  type="date"
                  name="birthDate"
                  className="input"
                  value={regBirthDate}
                  onChange={(e) => setRegBirthDate(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <label className="field">
                <span>Логин *</span>
                <input
                  type="text"
                  name="username"
                  className="input"
                  value={regUsername}
                  onChange={(e) => setRegUsername(e.target.value)}
                  autoComplete="username"
                  required
                  disabled={submitting}
                />
              </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <label className="field">
                <span>Email *</span>
                <input
                  type="email"
                  name="email"
                  className="input"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  autoComplete="email"
                  required
                  disabled={submitting}
                />
              </label>

              <label className="field">
                <span>Пароль *</span>
                <input
                  type="password"
                  name="password"
                  className="input"
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  disabled={submitting}
                />
              </label>
            </div>

            <label className="auth-checkbox">
              <input
                type="checkbox"
                checked={regConsent}
                onChange={(e) => setRegConsent(e.target.checked)}
                disabled={submitting}
                required
              />
              <span>
                Я даю согласие на обработку персональных данных в соответствии с 152-ФЗ *
              </span>
            </label>

            {error && <div className="auth-error" role="alert">{error}</div>}

            <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
              {submitting ? 'Отправка заявки…' : 'Подать заявку'}
            </button>

            <div className="auth-links" style={{ justifyContent: 'center' }}>
              <span>Уже есть аккаунт?</span>
              <button type="button" className="auth-link-btn" onClick={() => switchMode('login')}>
                Войти
              </button>
            </div>
          </>
        )}
      </form>
    );
  }

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
          value={loginPassword}
          onChange={(e) => setLoginPassword(e.target.value)}
          autoComplete="current-password"
          disabled={submitting}
        />
      </label>

      {error && <div className="auth-error" role="alert">{error}</div>}

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

export function AuthCard() {
  const [mode, setMode] = useState<AuthMode>('login');

  const titles: Record<AuthMode, { title: string; subtitle: string }> = {
    login: {
      title: 'Вход в систему',
      subtitle: 'Внутренний сервис платформы рейтинга спортсменов. Для просмотра данных войдите в систему.',
    },
    register: {
      title: 'Заявка на доступ',
      subtitle: 'Заполните форму для регистрации. Доступ открывается после одобрения администратором или капитаном.',
    },
    reset: {
      title: 'Сброс пароля',
      subtitle: 'Восстановление доступа к вашей учётной записи.',
    },
  };

  return (
    <div className="auth-card" style={mode === 'register' ? { maxWidth: 520 } : undefined}>
      <div className="auth-card__icon" aria-hidden="true">
        <Icon name="logo" />
      </div>
      <h1 className="auth-card__title">{titles[mode].title}</h1>
      <p className="auth-card__subtitle">{titles[mode].subtitle}</p>
      <AuthForm autoFocus={true} initialMode={mode} onModeChange={setMode} />
    </div>
  );
}

export function AuthModal() {
  const { isAuthModalOpen, closeAuthModal } = useAuth();
  const [mode, setMode] = useState<AuthMode>('login');

  useEffect(() => {
    if (!isAuthModalOpen) return;
    setMode('login');

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeAuthModal();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isAuthModalOpen, closeAuthModal]);

  if (!isAuthModalOpen) return null;

  const modalTitles: Record<AuthMode, string> = {
    login: 'Вход в систему',
    register: 'Регистрация и доступ',
    reset: 'Восстановление пароля',
  };

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
      <div className="modal-card" style={mode === 'register' ? { maxWidth: 520 } : undefined}>
        <button
          type="button"
          className="modal-close"
          onClick={closeAuthModal}
          aria-label="Закрыть окно авторизации"
        >
          <Icon name="close" />
        </button>

        <h2 id="auth-modal-title" className="modal-title">
          {modalTitles[mode]}
        </h2>
        <AuthForm autoFocus={true} initialMode={mode} onModeChange={setMode} />
      </div>
    </div>
  );
}
