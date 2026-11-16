// Каркас всех страниц: шапка, <main class="page">, подвал и нижняя навигация (перенос base.html).
import { Link, Outlet, ScrollRestoration, useMatches } from 'react-router-dom';
import { NAV_ITEMS, type Section } from '@/config/navigation';
import { Icon, Loader } from '@/components/ui';
import { useTheme } from '@/theme/ThemeProvider';
import { useAuth } from '@/context/AuthContext';
import { AuthCard, AuthModal } from '@/components/auth/AuthModal';

/** Данные маршрута (handle в src/routes.tsx), которые нужны каркасу. */
export interface RouteHandle {
  section?: Section;
  /** Дополнительный класс для <main class="page …">, например page--narrow. */
  pageClass?: string;
}

function useRouteHandle(): RouteHandle {
  const matches = useMatches();
  const handle: RouteHandle = {};
  for (const m of matches) Object.assign(handle, (m.handle as RouteHandle | undefined) ?? {});
  return handle;
}

function ThemeControls() {
  const { effective, setChoice, toggle } = useTheme();
  return (
    <>
      <div className="theme-switch" role="group" aria-label="Тема">
        <button type="button" aria-pressed={effective === 'light'} onClick={() => setChoice('light')}>Светлая</button>
        <button type="button" aria-pressed={effective === 'dark'} onClick={() => setChoice('dark')}>Тёмная</button>
      </div>
      <button
        type="button"
        className="theme-toggle"
        data-effective={effective}
        aria-label={effective === 'dark' ? 'Тема: тёмная. Включить светлую' : 'Тема: светлая. Включить тёмную'}
        aria-pressed={effective === 'dark'}
        onClick={toggle}
      >
        <span className="icon-moon"><Icon name="moon" /></span>
        <span className="icon-sun"><Icon name="sun" /></span>
      </button>
    </>
  );
}

function AuthControls() {
  const { user, openAuthModal, logout } = useAuth();

  if (user) {
    return (
      <div className="user-nav">
        <div className="user-badge" title={user.username}>
          <span className="user-badge__icon"><Icon name="user" className="icon-sm" /></span>
          <span className="user-badge__name">{user.display_name}</span>
          {user.role === 'admin' && <span className="chip chip--sm chip--brand">админ</span>}
        </div>
        <button
          type="button"
          className="btn btn--sm btn--ghost"
          onClick={logout}
          title="Выйти из учётной записи"
        >
          Выйти
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="btn btn--sm btn--ghost"
      onClick={openAuthModal}
    >
      Войти
    </button>
  );
}

export function AppLayout() {
  const { section = 'search', pageClass } = useRouteHandle();
  const { user, isAdmin, isLoading } = useAuth();
  const current = (s: Section) => (s === section ? 'page' : undefined);
  const visibleNavItems = NAV_ITEMS.filter((item) => item.section !== 'agent' || isAdmin);

  if (isLoading) {
    return (
      <div className="auth-gate-loading">
        <Loader text="Загрузка…" inCard={false} />
      </div>
    );
  }

  // Сервис для внутреннего пользования: без авторизации доступ ко всем данным закрыт
  if (!user) {
    return (
      <>
        <header className="app-header">
          <div className="app-header__inner">
            <div className="app-header__left">
              <span className="brand">
                <span className="brand__mark" aria-hidden="true"><Icon name="logo" /></span>
                <span className="brand__name">Рейтинг <br className="br" />спортсменов</span>
              </span>
            </div>
            <div className="app-header__right">
              <ThemeControls />
            </div>
          </div>
        </header>

        <main className="page page--narrow auth-gate-page">
          <AuthCard />
        </main>

        <footer className="app-footer">
          <div className="app-footer__inner">
            <span>Платформа для расчёта рейтинга спортсменов · внутренний сервис</span>
            <span>Для доступа к данным требуется авторизация</span>
          </div>
        </footer>
      </>
    );
  }

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <div className="app-header__left">
            <Link to="/" className="brand">
              <span className="brand__mark" aria-hidden="true"><Icon name="logo" /></span>
              <span className="brand__name">Рейтинг <br className="br" />спортсменов</span>
            </Link>
            <nav className="top-nav" aria-label="Разделы">
              {visibleNavItems.map((item) => (
                <Link key={item.section} to={item.to} aria-current={current(item.section)}>{item.label}</Link>
              ))}
            </nav>
          </div>
          <div className="app-header__right">
            <ThemeControls />
            <AuthControls />
          </div>
        </div>
      </header>

      <main className={pageClass ? `page ${pageClass}` : 'page'}>
        <Outlet />
      </main>

      <footer className="app-footer">
        <div className="app-footer__inner">
          <span>Платформа для расчёта рейтинга спортсменов · демонстрационный прототип</span>
          <span>Представленная информация может содержать ошибки</span>
        </div>
      </footer>

      <nav className="bottom-nav" aria-label="Разделы">
        {visibleNavItems.filter((item) => item.mobile).map((item) => (
          <Link key={item.section} to={item.to} aria-current={current(item.section)}>
            <Icon name={item.icon} />{item.label}
          </Link>
        ))}
      </nav>

      <AuthModal />
      <ScrollRestoration />
    </>
  );
}
