import { RatingView } from '@/features/rating';
import { SITE_TITLE, useDocumentTitle } from '@/shared/hooks';

export function RatingPage(): React.JSX.Element {
  useDocumentTitle(`Рейтинг — ${SITE_TITLE}`);
  return <RatingView />;
}
