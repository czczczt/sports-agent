import { SOURCE_KEYS, sourceName } from '@/shared/lib';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { DateRangePicker } from './DateRangePicker';
import styles from './EventFiltersForm.module.css';
import type { EventFilters } from './filters';
import { eventFilters } from './filters';

interface EventFiltersFormProps {
  initial: EventFilters;
  hasFilters: boolean;
  onApply: (f: EventFilters) => void;
  onReset: () => void;
}

export function EventFiltersForm({
  initial,
  hasFilters,
  onApply,
  onReset,
}: EventFiltersFormProps): React.JSX.Element {
  const { register, handleSubmit, watch, setValue } = useForm({
    defaultValues: initial,
    resolver: zodResolver(eventFilters),
  });
  const submit = handleSubmit((values) =>
    onApply({ ...values, query: values.query.trim(), city: values.city.trim() }),
  );

  return (
    <form className="card card--pad" id="events-filter-form" onSubmit={submit}>
      <div className="form-filters">
        <label className="field">
          Название забега
          <input
            className="input input--sm"
            type="text"
            {...register('query')}
            placeholder="Марафон, трейл..."
          />
        </label>
        <DateRangePicker
          from={watch('date_from')}
          to={watch('date_to')}
          onChange={(from, to) => {
            setValue('date_from', from);
            setValue('date_to', to);
          }}
        />
        <label className="field">
          Город
          <input className="input input--sm" type="text" {...register('city')} placeholder="Москва" />
        </label>
        <label className="field">
          Площадка
          <select className="input input--sm" {...register('source')}>
            <option value="">Все площадки</option>
            {SOURCE_KEYS.map((key) => (
              <option key={key} value={key}>
                {sourceName(key)}
              </option>
            ))}
          </select>
        </label>
        <div className={['row', styles.actions].join(' ')}>
          <button type="submit" className={['btn btn--primary btn--stretch-mobile', styles.button].join(' ')}>
            Применить
          </button>
          {hasFilters && (
            <button type="button" className={['btn btn--ghost', styles.button].join(' ')} onClick={onReset}>
              Сбросить
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
