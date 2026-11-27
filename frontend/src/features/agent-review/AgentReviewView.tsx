import { KEEP_SCROLL } from '@/shared/hooks';
import { useAuth } from '@/shared/session';
import { ErrorState, Icon, Loader } from '@/shared/ui';
import { useSearchParams } from 'react-router-dom';
import { RecipeReviewPanel } from './RecipeReviewPanel';
import { ReviewFilters } from './ReviewFilters';
import { ReviewList } from './ReviewList';
import { useAgentReview } from './useAgentReview';

export function AgentReviewView(): React.JSX.Element {
  const { isAdmin, openAuthModal } = useAuth();
  const [params, setParams] = useSearchParams();
  const status = params.get('status') || 'proposed';
  const source = params.get('source') || '';

  const { data, error, refetch: reload } = useAgentReview(status, source, isAdmin);

  if (!isAdmin) {
    return (
      <div className="card empty agent-auth-guard">
        <span className="empty__icon">
          <Icon name="user" />
        </span>
        <div className="strong">Требуются права администратора</div>
        <p className="small muted">
          Для просмотра и утверждения правок агента войдите под учётной записью администратора.
        </p>
        <button type="button" className="btn btn--primary" onClick={openAuthModal}>
          Войти как администратор
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="page-head">
        <div className="page-head__text">
          <h1 className="h1 h1-sm">Правки агента</h1>
          <p className="lead">
            Ход восстановления сбора протоколов и решения, которые требуют проверки оператора.
          </p>
        </div>
      </div>
      <RecipeReviewPanel />
      <section aria-labelledby="adapter-review-title">
        <h2 className="h2" id="adapter-review-title">
          Проверка адаптеров
        </h2>
        <ReviewFilters
          key={`${status}|${source}`}
          data={data}
          status={status}
          source={source}
          onApply={(st, src) => setParams(src ? { status: st, source: src } : { status: st }, KEEP_SCROLL)}
        />
        {error && !data ? (
          <ErrorState error={error} onRetry={reload} />
        ) : !data ? (
          <Loader />
        ) : (
          <ReviewList data={data} status={status} />
        )}
      </section>
    </>
  );
}
