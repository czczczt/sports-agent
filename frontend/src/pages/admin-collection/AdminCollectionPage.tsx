import { AdminCollectionView } from '@/features/admin-collection';
import { SITE_TITLE, useDocumentTitle } from '@/shared/hooks';

export function AdminCollectionPage(): React.JSX.Element {
  useDocumentTitle(`Обновление данных · ${SITE_TITLE}`);
  return <AdminCollectionView />;
}
