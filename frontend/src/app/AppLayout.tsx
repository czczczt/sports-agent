import { AuthCard, AuthModal } from '@/features/auth';
import { NAV_ITEMS, paths, type Section } from '@/shared/config';
import { useAuth } from '@/shared/session';
import { Icon, Loader } from '@/shared/ui';
import { Link, Outlet, ScrollRestoration, useMatches } from 'react-router-dom';
import { AuthControls } from './AuthControls';
import { MobileMenu } from './MobileMenu';
import { ThemeControls } from './ThemeControls';

export interface RouteHandle {
  section?: Section;
  pageClass?: string;
  isPublic?: boolean;
}

function useRouteHandle(): RouteHandle {
  const matches = useMatches();
  const handle: RouteHandle = {};
  for (const m of matches) Object.assign(handle, typeof m.handle === 'object' ? m.handle : {});
  return handle;
}

export function AppLayout(): React.JSX.Element {
  const { section = 'search', pageClass, isPublic } = useRouteHandle();
  const { user, isAdmin, isLoading } = useAuth();
  const current = (s: Section) => (s === section ? 'page' : undefined);
  const visibleNavItems = NAV_ITEMS.filter((item) => {
    if (item.section === 'status' || item.section === 'collection') return isAdmin;
    if (item.section === 'agent') return isAdmin;
    if (item.section === 'admin') return isAdmin || user?.role === 'captain';
    return true;
  });

  if (isLoading) {
    return (
      <div className="auth-gate-loading">
        <Loader text="Загрузка…" inCard={false} />
      </div>
    );
  }

  if (!user && !isPublic) {
    return (
      <>
        <a href="#content" className="skip-link">
          К содержимому
        </a>
        <header className="app-header">
          <div className="app-header__inner">
            <span className="brand">
              <span className="brand__mark" aria-hidden="true">
                <Icon name="logo" />
              </span>
              <span className="brand__name">
                Рейтинг <br />
                спортсменов
              </span>
            </span>
            <div className="app-header__right">
              <ThemeControls />
            </div>
          </div>
        </header>

        <main id="content" tabIndex={-1} className="page page--narrow auth-gate-page">
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
      <a href="#content" className="skip-link">
        К содержимому
      </a>
      <header className="app-header">
        <div className="app-header__inner">
          <Link to={paths.search} className="brand">
            <span className="brand__mark" aria-hidden="true">
              <Icon name="logo" />
            </span>
            <span className="brand__name">
              Рейтинг <br />
              спортсменов
            </span>
          </Link>
          {user && (
            <nav className="top-nav" aria-label="Разделы">
              {visibleNavItems.map((item) => (
                <Link key={item.section} to={item.to} aria-current={current(item.section)}>
                  {item.label}
                </Link>
              ))}
            </nav>
          )}
          <div className="app-header__right">
            <ThemeControls />
            {user ? (
              <>
                <div className="desktop-account">
                  <AuthControls />
                </div>
                <MobileMenu items={visibleNavItems.filter((item) => !item.mobile)} section={section} />
              </>
            ) : (
              <AuthControls />
            )}
          </div>
        </div>
      </header>

      <main id="content" tabIndex={-1} className={pageClass ? `page ${pageClass}` : 'page'}>
        <Outlet />
      </main>

      <footer className="app-footer">
        <div className="app-footer__inner">
          <span>Платформа для расчёта рейтинга спортсменов · демонстрационный прототип</span>
          <span>Представленная информация может содержать ошибки</span>
        </div>
      </footer>

      {user && (
        <nav className={isAdmin ? 'bottom-nav bottom-nav--admin' : 'bottom-nav'} aria-label="Разделы">
          {visibleNavItems
            .filter((item) => item.mobile)
            .map((item) => (
              <Link key={item.section} to={item.to} aria-current={current(item.section)}>
                <Icon name={item.icon} />
                {item.label}
              </Link>
            ))}
        </nav>
      )}

      <AuthModal />
      <ScrollRestoration />
    </>
  );
}
