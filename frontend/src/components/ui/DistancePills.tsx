// Переключатель дистанций старта (страница дистанции).
// Компьютер и планшет: пилюли переносятся на новые строки — видно все, прокрутки нет.
// Телефон (до 760 px): одна лента, листается пальцем; полоса прокрутки скрыта, а у края,
// за которым есть ещё дистанции, пилюли затухают (data-fade-start / data-fade-end в app.css).
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

export interface PillItem {
  id: number;
  label: string;
  to: string;
}

export function DistancePills({ items, activeId, label }: { items: PillItem[]; activeId: number; label: string }) {
  const ref = useRef<HTMLElement>(null);
  const [fade, setFade] = useState({ start: false, end: false });

  // Есть ли что листать влево/вправо (на десктопе лента переносится — там всегда false).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const max = el.scrollWidth - el.clientWidth;
      setFade({ start: el.scrollLeft > 2, end: max - el.scrollLeft > 2 });
    };
    update();
    el.addEventListener('scroll', update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener('scroll', update);
      ro.disconnect();
    };
  }, [items.length]);

  // Выбранная дистанция — в видимой части ленты. Считаем вручную: scrollIntoView сдвинул бы и страницу.
  useLayoutEffect(() => {
    const el = ref.current;
    const active = el?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!el || !active || el.scrollWidth <= el.clientWidth) return;
    el.scrollLeft = active.offsetLeft - el.offsetLeft - (el.clientWidth - active.offsetWidth) / 2;
  }, [activeId]);

  return (
    <nav ref={ref} className="pills" aria-label={label}
      data-fade-start={fade.start || undefined} data-fade-end={fade.end || undefined}>
      {items.map((it) => (
        <Link key={it.id} to={it.to} className="pill" aria-current={it.id === activeId ? 'page' : undefined}>{it.label}</Link>
      ))}
    </nav>
  );
}
