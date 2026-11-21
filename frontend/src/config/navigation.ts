// Разделы сайта для верхней (десктоп) и нижней (телефон) навигации.
// Новый раздел: добавьте его сюда и укажите section в handle маршрута (src/routes.tsx).
import type { IconName } from '@/components/ui/Icon';

export type Section = 'events' | 'rating' | 'search' | 'agent' | 'admin' | 'status';

export interface NavItem {
  section: Section;
  to: string;
  label: string;
  icon: IconName;
  mobile: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { section: 'events', to: '/events-view', label: 'Старты', icon: 'calendar', mobile: true },
  { section: 'rating', to: '/rating-view', label: 'Рейтинг', icon: 'trophy', mobile: true },
  { section: 'search', to: '/', label: 'Найти себя', icon: 'user', mobile: true },
  { section: 'admin', to: '/admin/requests', label: 'Заявки', icon: 'flag', mobile: false },
  { section: 'agent', to: '/agent-review', label: 'Правки агента', icon: 'spark', mobile: false },
  { section: 'status', to: '/status', label: 'Статус', icon: 'spark', mobile: false },
];
