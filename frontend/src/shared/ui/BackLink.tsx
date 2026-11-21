import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from './Icon';

interface BackLinkProps {
  to: string;
  children: ReactNode;
}

export function BackLink({ to, children }: BackLinkProps): React.JSX.Element {
  return (
    <Link to={to} className="back-link">
      <Icon name="back" className="icon-sm" />
      {children}
    </Link>
  );
}
