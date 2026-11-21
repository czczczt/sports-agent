import { Icon } from './Icon';

interface ErrorStateProps {
  error: Error;
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps): React.JSX.Element {
  return (
    <div className="card empty" role="alert">
      <span className="empty__icon">
        <Icon name="empty" />
      </span>
      <div className="strong">Не удалось загрузить данные</div>
      <p className="small muted">{error.message}</p>
      {onRetry && (
        <button type="button" className="btn btn--ghost" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}
