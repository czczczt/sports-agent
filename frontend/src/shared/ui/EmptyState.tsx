import type { ReactNode } from 'react';
import type { IconName } from './Icon';
import { Icon } from './Icon';

interface EmptyStateProps {
  icon?: IconName | null;
  title?: ReactNode;
  text?: ReactNode;
  inCard?: boolean;
}

export function EmptyState({
  icon = 'empty',
  title,
  text,
  inCard = true,
}: EmptyStateProps): React.JSX.Element {
  return (
    <div className={inCard ? 'card empty' : 'empty'}>
      {icon && (
        <span className="empty__icon">
          <Icon name={icon} />
        </span>
      )}
      {title && <div className="strong">{title}</div>}
      {text && <p className="small muted">{text}</p>}
    </div>
  );
}
