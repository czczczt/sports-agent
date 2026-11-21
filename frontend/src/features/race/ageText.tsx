import type { RaceProtocolItem } from '@/shared/api';

export function ageText(r: RaceProtocolItem): string {
  if (r.age != null && r.age > 0) return String(r.age);
  if (r.age === 0 || r.birth_year === 2026) return '1';
  return '';
}
