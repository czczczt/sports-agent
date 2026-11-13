// Мелкие общие элементы интерфейса (перенос макросов _ui.html и повторяющейся разметки).
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '@/api/client';
import { Icon, type IconName } from './Icon';

export { Icon };
export type { IconName };

/** «← Раздел» над заголовком страницы. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="back-link">
      <Icon name="back" className="icon-sm" />
      {children}
    </Link>
  );
}

/** Бейдж статуса результата: FIN / DNF / DSQ / прочие. */
export function StatusChip({ status }: { status?: string | null }) {
  if (status === 'FIN') return <span className="chip chip--sm chip--brand">финиш</span>;
  if (status === 'DNF') return <span className="chip chip--sm chip--pending">DNF</span>;
  if (status === 'DSQ') return <span className="chip chip--sm chip--error">DSQ</span>;
  return <span className="chip chip--sm chip--muted">{status || '—'}</span>;
}

/** Пустое состояние: иконка, заголовок, пояснение. inCard — отдельной карточкой. */
export function EmptyState({ icon = 'empty', title, text, inCard = true }: {
  icon?: IconName | null;
  title?: ReactNode;
  text?: ReactNode;
  inCard?: boolean;
}) {
  return (
    <div className={inCard ? 'card empty' : 'empty'}>
      {icon && <span className="empty__icon"><Icon name={icon} /></span>}
      {title && <div className="strong">{title}</div>}
      {text && <p className="small muted">{text}</p>}
    </div>
  );
}

/** Индикатор загрузки страницы или блока. */
export function Loader({ text = 'Загрузка…', inCard = true }: { text?: string; inCard?: boolean }) {
  return (
    <div className={inCard ? 'card empty' : 'empty'} role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p className="small muted">{text}</p>
    </div>
  );
}

/** Ошибка загрузки с кнопкой повтора. */
export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="card empty" role="alert">
      <span className="empty__icon"><Icon name="empty" /></span>
      <div className="strong">Не удалось загрузить данные</div>
      <p className="small muted">{error.message}</p>
      {onRetry && <button type="button" className="btn btn--ghost" onClick={onRetry}>Повторить</button>}
    </div>
  );
}

/** Страница не найдена (неизвестный адрес или 404 от API). */
export function NotFound({ title = 'Страница не найдена', text, backTo = '/', backLabel = 'Найти себя' }: {
  title?: string;
  text?: ReactNode;
  backTo?: string;
  backLabel?: string;
}) {
  return (
    <>
      <BackLink to={backTo}>{backLabel}</BackLink>
      <EmptyState title={title} text={text ?? 'Проверьте адрес или вернитесь на главную.'} />
    </>
  );
}

/** Стандартная обработка состояний запроса: загрузка → ошибка/404 → содержимое. */
export function PageState({ loading, error, hasData, notFound, onRetry, children }: {
  loading: boolean;
  error: Error | null;
  hasData: boolean;
  notFound?: ReactNode;
  onRetry?: () => void;
  children: () => ReactNode;
}) {
  if (error instanceof ApiError && error.status === 404) return <>{notFound ?? <NotFound />}</>;
  if (error && !hasData) return <ErrorState error={error} onRetry={onRetry} />;
  if (!hasData) return loading ? <Loader /> : null;
  return <>{children()}</>;
}

/** Вертикальное многоточие между строкой «это вы» и началом таблицы. */
export function GapDots() {
  return <>&bull;<br />&bull;<br />&bull;</>;
}
