import { StatusView } from '@/features/status';
import { SITE_TITLE, useDocumentTitle } from '@/shared/hooks';

export function StatusPage(): React.JSX.Element {
  useDocumentTitle(`Статус системы · ${SITE_TITLE}`);
  return <StatusView />;
}
