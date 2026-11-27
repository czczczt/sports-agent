import { ErrorState, Loader } from '@/shared/ui';
import { RepairCard } from './RepairCard';
import { useRepairs } from './useRepairs';

export function RecipeReviewPanel(): React.JSX.Element {
  const { data, error, isFetching: loading, refetch: reload } = useRepairs();

  return (
    <section aria-labelledby="recipe-review-title">
      <div className="page-head">
        <h2 className="h2" id="recipe-review-title">
          Агент восстановления сбора
        </h2>
        <button type="button" className="btn" onClick={() => void reload()}>
          Обновить
        </button>
      </div>
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {!loading && data?.length === 0 && <p className="muted">Запусков ремонта пока нет.</p>}
      {data?.map((repair) => (
        <RepairCard key={repair.id} repair={repair} />
      ))}
    </section>
  );
}
