import { AdminRequestsView } from '@/features/admin-requests';
import { SITE_TITLE, useDocumentTitle } from '@/shared/hooks';

export function AdminRequestsPage(): React.JSX.Element {
  useDocumentTitle(`Заявки и модерация · ${SITE_TITLE}`);
  return <AdminRequestsView />;
}
