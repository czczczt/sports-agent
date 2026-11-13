// Каталог стартов (/events-view). Перенос events_catalog.html: фильтры в адресе, группировка по месяцам.
import { Fragment, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { eventsApi, type EventFilters } from '@/api/endpoints';
import type { EventItem } from '@/api/types';
import { DateRangePicker } from '@/components/forms/DateRangePicker';
import { EmptyState, ErrorState, Loader } from '@/components/ui';
import { useApi } from '@/hooks/useApi';
import { KEEP_SCROLL } from '@/hooks/keepScroll';
import { SITE_TITLE, useDocumentTitle } from '@/hooks/useDocumentTitle';
import { dateRu, monthTitle, plural, SOURCE_KEYS, sourceName } from '@/lib/format';

const FILTER_KEYS = ['query', 'date_from', 'date_to', 'city', 'source'] as const;

function readFilters(params: URLSearchParams): Required<EventFilters> {
  return {
    // title — прежний алиас query
    query: params.get('query') || params.get('title') || '',
    date_from: params.get('date_from') || '',
    date_to: params.get('date_to') || '',
    city: params.get('city') || '',
    source: params.get('source') || '',
  };
}

const monthKey = (ev: EventItem) => (ev.date_begin || '').slice(0, 7);

export function EventsPage() {
  useDocumentTitle(`Старты — ${SITE_TITLE}`);
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const filtersKey = FILTER_KEYS.map((k) => filters[k]).join('|');

  const { data: events, error, loading, reload } = useApi(
    (signal) => eventsApi.list(filters, signal),
    [filtersKey],
  );

  const apply = (next: Required<EventFilters>) => {
    const q: Record<string, string> = {};
    for (const k of FILTER_KEYS) if (next[k]) q[k] = next[k];
    setParams(q, KEEP_SCROLL);
  };
  const hasFilters = FILTER_KEYS.some((k) => filters[k]);
  const count = events?.length ?? 0;

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1">Старты</h1>
          <p className="small muted">
            Собранные соревнования и протоколы дистанций · на странице {events ? `${count} ${plural(count, 'старт', 'старта', 'стартов')}` : '…'}
          </p>
        </div>
      </div>

      <EventFiltersForm key={filtersKey} initial={filters} hasFilters={hasFilters} onApply={apply} onReset={() => setParams({}, KEEP_SCROLL)} />

      {error && !events ? <ErrorState error={error} onRetry={reload} />
        : !events || (loading && !events.length) ? <Loader />
        : events.length ? <EventsList events={events} />
        : <EmptyState icon="calendar" title="Стартов не найдено" text="Измените параметры поиска или сбросьте фильтры." />}
    </>
  );
}

function EventFiltersForm({ initial, hasFilters, onApply, onReset }: {
  initial: Required<EventFilters>;
  hasFilters: boolean;
  onApply: (f: Required<EventFilters>) => void;
  onReset: () => void;
}) {
  const [form, setForm] = useState(initial);
  const set = (k: keyof EventFilters, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onApply({ ...form, query: form.query.trim(), city: form.city.trim() });
  };

  return (
    <form className="card card--pad" id="events-filter-form" onSubmit={submit}>
      <div className="form-filters">
        <label className="field">Название забега
          <input className="input input--sm" type="text" name="query" value={form.query}
            onChange={(e) => set('query', e.target.value)} placeholder="Марафон, трейл..." />
        </label>
        <DateRangePicker from={form.date_from} to={form.date_to}
          onChange={(from, to) => setForm((f) => ({ ...f, date_from: from, date_to: to }))} />
        <label className="field">Город
          <input className="input input--sm" type="text" name="city" value={form.city}
            onChange={(e) => set('city', e.target.value)} placeholder="Москва" />
        </label>
        <label className="field">Площадка
          <select className="input input--sm" name="source" value={form.source} onChange={(e) => set('source', e.target.value)}>
            <option value="">Все площадки</option>
            {SOURCE_KEYS.map((key) => <option key={key} value={key}>{sourceName(key)}</option>)}
          </select>
        </label>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <button type="submit" className="btn btn--primary btn--stretch-mobile" style={{ minHeight: 40 }}>Применить</button>
          {hasFilters && (
            <Link to="/events-view" className="btn btn--ghost" style={{ minHeight: 40 }} onClick={(e) => { e.preventDefault(); onReset(); }}>Сбросить</Link>
          )}
        </div>
      </div>
    </form>
  );
}

function EventsList({ events }: { events: EventItem[] }) {
  const isNewMonth = (i: number) => i === 0 || monthKey(events[i]) !== monthKey(events[i - 1]);

  return (
    <>
      {/* Десктоп: таблица, сгруппированная по месяцам */}
      <section className="card card--clip only-desktop">
        <div className="table-wrap">
          <table className="table" style={{ minWidth: 760 }}>
            <thead>
              <tr>
                <th scope="col" style={{ width: 110 }}>Дата</th>
                <th scope="col">Старт</th>
                <th scope="col">Площадка</th>
                <th scope="col">Место</th>
                <th scope="col" className="right">Дистанций</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <Fragment key={ev.id}>
                  {isNewMonth(i) && (
                    <tr className="group-row"><th scope="rowgroup" colSpan={5} className="muted">{monthTitle(ev.date_begin)}</th></tr>
                  )}
                  <tr>
                    <td className="num muted nowrap">{dateRu(ev.date_begin)}</td>
                    <td>
                      <Link to={`/events-view/${ev.id}`} className="cell-title">{ev.title}</Link>
                      {ev.races.length > 0 && (
                        <div className="chips" style={{ marginTop: 6 }}>
                          {ev.races.map((r) => (
                            <Link key={r.id} to={`/races-view/${r.id}`} className="chip chip--sm">
                              {r.name_raw}{!!r.total_count && <> <span className="chip__count num">{r.total_count}</span></>}
                            </Link>
                          ))}
                        </div>
                      )}
                    </td>
                    <td><span className="chip chip--sm">{sourceName(ev.source_name)}</span></td>
                    <td className="muted">{ev.place || ev.address || '—'}</td>
                    <td className="num right strong">{ev.races.length}</td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Телефон: список строк */}
      <section className="card card--clip only-mobile">
        {events.map((ev, i) => (
          <Fragment key={ev.id}>
            {isNewMonth(i) && (
              <div className={`small muted strong month-label${i > 0 ? ' month-label--sep' : ''}`}>{monthTitle(ev.date_begin)}</div>
            )}
            <Link to={`/events-view/${ev.id}`} className="list-row">
              <div style={{ minWidth: 0 }}>
                <div className="list-row__title">{ev.title}</div>
                <div className="list-row__meta num">{dateRu(ev.date_begin)}{(ev.place || ev.address) && ` · ${ev.place || ev.address}`}</div>
              </div>
              <div className="list-row__end">
                <span className="chip chip--sm">{sourceName(ev.source_name)}</span>
                <div className="list-row__meta num">{ev.races.length} {plural(ev.races.length, 'дистанция', 'дистанции', 'дистанций')}</div>
              </div>
            </Link>
          </Fragment>
        ))}
      </section>
    </>
  );
}
