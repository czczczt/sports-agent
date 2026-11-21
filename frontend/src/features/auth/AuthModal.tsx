import { useAuth } from '@/shared/session';
import { Icon } from '@/shared/ui';
import { useEffect, useState } from 'react';
import { AuthForm, type AuthMode } from './AuthForm';
import layout from './AuthForm.module.css';

export function AuthModal(): React.JSX.Element | null {
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
      className={layout.modalOverlay}
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) closeAuthModal();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
    >
      <div className={layout.modalCard} data-mode={mode}>
        <button
          type="button"
          className={layout.modalClose}
          onClick={closeAuthModal}
          aria-label="Закрыть окно авторизации"
        >
          <Icon name="close" />
        </button>

        <h2 id="auth-modal-title" className={layout.modalTitle}>
          {modalTitles[mode]}
        </h2>
        <AuthForm mode={mode} switchMode={setMode} />
      </div>
    </div>
  );
}
