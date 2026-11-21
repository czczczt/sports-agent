import { useQuery } from '@tanstack/react-query';
import { ratingApi } from './api';

export const ratingFormulaKey = () => ['rating-formula'] as const;

export function useRatingFormula() {
  return useQuery({ queryKey: ratingFormulaKey(), queryFn: ({ signal }) => ratingApi.formula(signal) });
}
