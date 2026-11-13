// Форматирование для интерфейса. Перенесено из макросов app/templates/_ui.html один к одному,
// чтобы строки на страницах совпадали с прежним серверным рендерингом.

const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

/** «2025-12-21...» → «21.12.2025»; пусто → «—». */
export function dateRu(d?: string | null): string {
  if (d && d.length >= 10) return `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}`;
  return d || '—';
}

/** «2025-12-21...» → «Декабрь 2025». */
export function monthTitle(d?: string | null): string {
  const m = d && d.length >= 7 ? parseInt(d.slice(5, 7), 10) : 0;
  return m >= 1 && m <= 12 ? `${MONTHS[m - 1]} ${d!.slice(0, 4)}` : 'Без даты';
}

/** «Иванов Иван» → «ИИ». */
export function initials(name?: string | null): string {
  const parts = (name || '?').split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[1][0] : '')).toUpperCase();
}

/** Пол в одну букву: M/F → М/Ж. */
export function genderLabel(g?: string | null): string {
  if (!g) return '';
  if (['M', 'М', 'm'].includes(g)) return 'М';
  if (['F', 'Ж', 'W', 'f', 'w'].includes(g)) return 'Ж';
  return g;
}

const SOURCE_NAMES: Record<string, string> = {
  russiarunning: 'RussiaRunning',
  timerman: 'Timerman',
  runc: 'RUNC',
  grom: 'Grom',
  'probeg.org': 'probeg',
  probeg: 'probeg',
};

/** Код площадки → название для людей. */
export function sourceName(s?: string | null): string {
  return (s && SOURCE_NAMES[s]) || s || '';
}

/** Площадки, доступные в фильтре каталога стартов. */
export const SOURCE_KEYS = ['russiarunning', 'timerman', 'runc', 'grom'] as const;

const pad2 = (n: number) => String(n).padStart(2, '0');

/** Секунды → «Ч:ММ:СС» или «ММ:СС»; пусто → «—». */
export function hms(s?: number | null): string {
  if (!s) return '—';
  const t = Math.round(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  return h > 0 ? `${h}:${pad2(m)}:${pad2(sec)}` : `${pad2(m)}:${pad2(sec)}`;
}

/** Русское склонение: plural(3, 'старт', 'старта', 'стартов') → «старта». */
export function plural(n: number, one: string, few: string, many: string): string {
  const n10 = n % 10;
  const n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return one;
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return few;
  return many;
}

/** Число и слово в нужной форме: «3 старта». */
export function countLabel(n: number, one: string, few: string, many: string): string {
  return `${n} ${plural(n, one, few, many)}`;
}

/** Один знак после запятой, как '%.1f' в шаблонах: 4797.46 → «4797.5». */
export function fixed1(v: number): string {
  return v.toFixed(1);
}

/**
 * Как Jinja-фильтр round(digits) с выводом float: 111 → «111.0», 6.84 → «6.8».
 * toFixed округляет по точному двоичному значению, как Python: 21.65 → «21.6», а не 21.7.
 */
export function pyRound(v: number, digits: number): string {
  const r = Number(v.toFixed(digits));
  return Number.isInteger(r) ? `${r}.0` : String(r);
}

/** Строка «год · город · пол · клуб» для карточек спортсмена. */
export function athleteMeta(
  a: { birth_year?: number | null; city?: string | null; region?: string | null; gender?: string | null; club?: string | null },
  withClub = true,
): string {
  let s = a.birth_year ? String(a.birth_year) : 'год не указан';
  if (a.city || a.region) s += ` · ${a.city || a.region}`;
  if (a.gender) s += ` · ${genderLabel(a.gender)}`;
  if (withClub && a.club) s += ` · ${a.club}`;
  return s;
}

/** Date → «YYYY-MM-DD» (локальная дата, без сдвига в UTC). */
export function toIsoDate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** Date → «ДД.ММ.ГГГГ». */
export function formatDateRu(d: Date): string {
  return `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`;
}

/** «YYYY-MM-DD...» → Date (локальная) или null. */
export function parseIsoDate(s?: string | null): Date | null {
  if (!s || !/^\d{4}-\d{2}-\d{2}/.test(s)) return null;
  const [y, m, d] = s.slice(0, 10).split('-').map((p) => parseInt(p, 10));
  return new Date(y, m - 1, d);
}

/** ISO-дата и время → «ДД.ММ.ГГГГ ЧЧ:ММ» (как strftime('%d.%m.%Y %H:%M')). */
export function dateTimeRu(iso?: string | null): string {
  if (!iso) return '';
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}` : iso;
}
