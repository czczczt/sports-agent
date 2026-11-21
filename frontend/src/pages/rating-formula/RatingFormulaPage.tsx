import { RatingFormulaView } from '@/features/rating-formula';
import { useDocumentTitle } from '@/shared/hooks';

export function RatingFormulaPage(): React.JSX.Element {
  useDocumentTitle('Как посчитано — беговой рейтинг');
  return <RatingFormulaView />;
}
