import type { ReactNode } from 'react';
import { BackLink } from './BackLink';
import { EmptyState } from './EmptyState';

interface NotFoundProps {
  title?: string;
  text?: ReactNode;
  backTo?: string;
  backLabel?: string;
}

export function NotFound({
  title = 'Страница не найдена',
  text,
  backTo = '/',
  backLabel = 'Найти себя',
}: NotFoundProps): React.JSX.Element {
  return (
    <>
      <BackLink to={backTo}>{backLabel}</BackLink>
      <EmptyState title={title} text={text ?? 'Проверьте адрес или вернитесь на главную.'} />
    </>
  );
}
