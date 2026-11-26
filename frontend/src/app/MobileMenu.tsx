import { type NavItem, type Section } from '@/shared/config';
import { Icon } from '@/shared/ui';
import { useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AuthControls } from './AuthControls';

export function MobileMenu({ items, section }: { items: NavItem[]; section: Section }) {
  const menu = useRef<HTMLDetailsElement>(null);
  const location = useLocation();

  useEffect(() => {
    const details = menu.current;
    if (!details) return;
    details.open = false;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !details.contains(event.target)) details.open = false;
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && details.open) {
        details.open = false;
        details.querySelector('summary')?.focus();
      }
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [location.key]);

  return (
    <details
      className="mobile-menu"
      ref={menu}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
      }}
    >
      <summary
        className="btn btn--ghost"
        data-active={items.some((item) => item.section === section) || undefined}
      >
        <Icon name="menu" /> Меню
      </summary>
      <div className="mobile-menu__panel">
        <nav aria-label="Дополнительные разделы">
          {items.map((item) => (
            <Link
              key={item.section}
              to={item.to}
              aria-current={item.section === section ? 'page' : undefined}
            >
              <Icon name={item.icon} /> {item.label}
            </Link>
          ))}
        </nav>
        <AuthControls />
      </div>
    </details>
  );
}
