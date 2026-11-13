// Каркас всех страниц: шапка, <main class="page">, подвал и нижняя навигация (перенос base.html).
import { Link, Outlet, ScrollRestoration, useMatches } from 'react-router-dom';
import { NAV_ITEMS, type Section } from '@/config/navigation';
import { Icon } from '@/components/ui/Icon';
import { useTheme } from '@/theme/ThemeProvider';

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

export function AppLayout() {
  const { section = 'search', pageClass } = useRouteHandle();
  const current = (s: Section) => (s === section ? 'page' : undefined);

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
              {NAV_ITEMS.map((item) => (
                <Link key={item.section} to={item.to} aria-current={current(item.section)}>{item.label}</Link>
              ))}
            </nav>
          </div>
          <div className="app-header__right">
            <ThemeControls />
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
        {NAV_ITEMS.filter((item) => item.mobile).map((item) => (
          <Link key={item.section} to={item.to} aria-current={current(item.section)}>
            <Icon name={item.icon} />{item.label}
          </Link>
        ))}
      </nav>

      <ScrollRestoration />
    </>
  );
}
