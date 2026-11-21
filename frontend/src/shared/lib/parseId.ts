import { z } from 'zod';
const positiveId = z.coerce.number().int().positive().safe().nullable().catch(null);

export function parseId(value: string | null | undefined): number | null {
  return positiveId.parse(value);
}
