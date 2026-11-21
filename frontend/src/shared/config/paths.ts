export const routes = {
  search: '/',
  status: '/status',
  resetPassword: '/reset-password',
  athlete: '/athletes-view/:athleteId',
  rating: '/rating-view',
  ratingFormula: '/rating-formula',
  events: '/events-view',
  event: '/events-view/:eventId',
  race: '/races-view/:raceId',
  adminRequests: '/admin/requests',
  admin: '/admin',
  agentReview: '/agent-review',
} as const;

export const paths = {
  ...routes,
  athlete: (id: number) => routes.athlete.replace(':athleteId', String(id)),
  event: (id: number) => routes.event.replace(':eventId', String(id)),
  race: (id: number, athleteId?: number | null) =>
    routes.race.replace(':raceId', String(id)) + (athleteId ? '?athlete_id=' + athleteId : ''),
  ratingFor: (athleteId: number) => routes.rating + '?athlete_id=' + athleteId,
};
