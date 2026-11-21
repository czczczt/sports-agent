import { useAuth } from '@/shared/session';
import { Icon } from '@/shared/ui';
import { useState } from 'react';

export function AuthControls(): React.JSX.Element {
  const { user, openAuthModal, logout } = useAuth();

  const [logoutError, setLogoutError] = useState<string>();
  if (user) {
    return (
      <div className="user-nav">
        <div className="user-badge" title={user.username}>
          <span className="user-badge__icon">
            <Icon name="user" className="icon-sm" />
          </span>
          <span className="user-badge__name">{user.display_name}</span>
          {user.role === 'admin' && <span className="chip chip--sm chip--brand">админ</span>}
        </div>
        <button
          type="button"
          className="btn btn--sm btn--ghost"
          onClick={() =>
            logout().catch((error: unknown) =>
              setLogoutError(error instanceof Error ? error.message : 'Ошибка выхода'),
            )
          }
          title="Выйти из учётной записи"
        >
          Выйти
        </button>
      </div>
    );
  }

  return (
    <>
      {logoutError && <span role="alert">{logoutError}</span>}
      <button type="button" className="btn btn--sm btn--ghost" onClick={openAuthModal}>
        Войти
      </button>
    </>
  );
}
