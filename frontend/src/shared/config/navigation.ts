import { paths } from './paths';
import type { IconName } from '@/shared/ui';

export type Section = 'events' | 'rating' | 'search' | 'agent' | 'admin' | 'status';

export interface NavItem {
  section: Section;
  to: string;
  label: string;
  icon: IconName;
  mobile: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { section: 'events', to: paths.events, label: 'Старты', icon: 'calendar', mobile: true },
  { section: 'rating', to: paths.rating, label: 'Рейтинг', icon: 'trophy', mobile: true },
  { section: 'search', to: paths.search, label: 'Найти себя', icon: 'user', mobile: true },
  { section: 'admin', to: paths.adminRequests, label: 'Заявки', icon: 'flag', mobile: false },
  { section: 'agent', to: paths.agentReview, label: 'Правки агента', icon: 'spark', mobile: false },
  { section: 'status', to: paths.status, label: 'Статус', icon: 'spark', mobile: false },
];
