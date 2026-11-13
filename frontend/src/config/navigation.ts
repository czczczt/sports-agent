// Разделы сайта для верхней (десктоп) и нижней (телефон) навигации.
// Новый раздел: добавьте его сюда и укажите section в handle маршрута (src/routes.tsx).
import type { IconName } from '@/components/ui/Icon';

export type Section = 'events' | 'rating' | 'search' | 'agent';

export interface NavItem {
  section: Section;
  to: string;
  label: string;
  icon: IconName;
  /** Показывать в нижней панели на телефоне. */
  mobile: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { section: 'events', to: '/events-view', label: 'Старты', icon: 'calendar', mobile: true },
  { section: 'rating', to: '/rating-view', label: 'Рейтинг', icon: 'trophy', mobile: true },
  { section: 'search', to: '/', label: 'Найти себя', icon: 'user', mobile: true },
  { section: 'agent', to: '/agent-review', label: 'Правки агента', icon: 'spark', mobile: false },
];
