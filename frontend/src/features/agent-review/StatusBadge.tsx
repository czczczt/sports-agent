interface StatusBadgeProps {
  status: string;
}

export function StatusBadge({ status }: StatusBadgeProps): React.JSX.Element {
  if (status === 'proposed') return <span className="chip chip--sm chip--pending">ждёт решения</span>;
  if (['approved', 'resolved', 'known'].includes(status))
    return <span className="chip chip--sm chip--brand">{status}</span>;
  if (status === 'rejected') return <span className="chip chip--sm chip--error">rejected</span>;
  return <span className="chip chip--sm chip--muted">{status}</span>;
}
