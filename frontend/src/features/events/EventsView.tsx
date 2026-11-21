import { plural } from '@/shared/lib';
import { AsyncView, EmptyState } from '@/shared/ui';
import { EventFiltersForm } from './EventFiltersForm';
import { EventsList } from './EventsList';
import type { EventFilters } from './filters';
import { useEvents } from './useEvents';

export interface EventsViewProps {
  filters: EventFilters;
  onApply: (filters: EventFilters) => void;
  onReset: () => void;
}

export function EventsView({ filters, onApply, onReset }: EventsViewProps): React.JSX.Element {
  const filtersKey = JSON.stringify(filters);

  const query = useEvents(filters);
  const events = query.data;

  const hasFilters = Object.values(filters).some(Boolean);
  const count = events?.length ?? 0;

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1">Старты</h1>
          <p className="small muted">
            Собранные соревнования и протоколы дистанций · на странице{' '}
            {events ? `${count} ${plural(count, 'старт', 'старта', 'стартов')}` : '…'}
          </p>
        </div>
      </div>

      <EventFiltersForm
        key={filtersKey}
        initial={filters}
        hasFilters={hasFilters}
        onApply={onApply}
        onReset={onReset}
      />

      <AsyncView query={query}>
        {(events) =>
          events.length ? (
            <EventsList events={events} />
          ) : (
            <EmptyState
              icon="calendar"
              title="Стартов не найдено"
              text="Измените параметры поиска или сбросьте фильтры."
            />
          )
        }
      </AsyncView>
    </>
  );
}
