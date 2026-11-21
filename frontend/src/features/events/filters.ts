import { z } from 'zod';
export const eventFilters = z.object({
  query: z.string(),
  city: z.string(),
  source: z.string(),
  date_from: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .catch(''),
  date_to: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/)
    .catch(''),
});

export type EventFilters = z.infer<typeof eventFilters>;
