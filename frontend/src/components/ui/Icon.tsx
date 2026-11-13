// Inline stroke-SVG иконки в стиле макета (перенос макроса icon() из _ui.html).
// Новая иконка: добавьте её path в ICONS — имя сразу станет доступно в типе IconName.
import type { ReactNode } from 'react';

const ICONS = {
  logo: <path d="M4 20v-7h5v7M9 20V7h6v13M15 20v-5h5v5" />,
  back: <path d="M15 6l-6 6 6 6" />,
  calendar: (<><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></>),
  user: (<><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></>),
  run: (<><circle cx="14" cy="4.5" r="2" /><path d="M8 21l3-6 3 2v5M6 12l3-4h5l2 4 3 1M11 15l-1-4" /></>),
  pin: (<><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></>),
  search: (<><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></>),
  external: <path d="M7 17L17 7M9 7h8v8" />,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />,
  sun: (<><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>),
  trophy: <path d="M8 4h8v5a4 4 0 0 1-8 0V4zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 21h8M9 17h6" />,
  spark: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16z" />,
  flag: <path d="M5 21V4h11l-1.5 4L16 12H5" />,
  chevron: <path d="M9 6l6 6-6 6" />,
  empty: (<><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5M8.5 11h5" /></>),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof ICONS;

export function Icon({ name, className = 'icon' }: { name: IconName; className?: string }) {
  return (
    <svg className={className} aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      {ICONS[name]}
    </svg>
  );
}
