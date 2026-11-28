import type { AgentReviewPage as AgentReviewData } from '@/shared/api';
import { EmptyState } from '@/shared/ui';
import { ReviewCard } from './ReviewCard';

interface ReviewListProps {
  data: AgentReviewData;
  status: string;
  hideEmpty?: boolean;
}

export function ReviewList({ data, status, hideEmpty = false }: ReviewListProps): React.JSX.Element {
  const items = data.items;
  return (
    <>
      {data.db_error && (
        <div className="card card--pending" role="alert">
          <p className="strong">Управление агентом временно недоступно</p>
          <p className="small">{data.db_error}</p>
          <p className="small muted">
            Для этого экрана нужна PostgreSQL-база парсера и переменная окружения <code>DATABASE_URL</code>.
          </p>
        </div>
      )}

      {!items.length && !hideEmpty && (
        <EmptyState
          title={`Предложений нет${status !== 'all' ? ` в статусе «${status}»` : ''}`}
          text="Все задачи проверены или находятся в других вкладках."
        />
      )}

      {items.map((it) => (
        <ReviewCard key={it.issue_id} item={it} defaultAuthor={data.default_author} />
      ))}
    </>
  );
}
