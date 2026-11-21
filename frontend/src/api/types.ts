export interface User {
  id?: number;
  username: string;
  role: 'user' | 'captain' | 'admin';
  status?: string;
  display_name: string;
  athlete_id?: number | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  middle_name?: string | null;
  birth_date?: string | null;
  city?: string | null;
  consent: boolean;
  consent_version?: string;
}

export interface RegisterResponse {
  status: string;
  message: string;
  user_id: number;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  new_password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface AthleteCandidate {
  id: number;
  display_name: string;
  birth_year?: number | null;
  gender?: string | null;
  city?: string | null;
  region?: string | null;
  club?: string | null;
  starts_count: number;
  results_count: number;
}

export interface AthleteResultItem {
  result_id: number;
  event_id: number;
  event_title: string;
  event_date?: string | null;
  source_name: string;
  race_id: number;
  distance_name: string;
  norm_distance?: string | null;
  distance_m?: number | null;
  place_abs?: number | string | null;
  place_gender?: number | string | null;
  total_finishers?: number | null;
  total_participants?: number | null;
  chip_time_s?: number | null;
  gun_time_s?: number | null;
  time_formatted: string;
  pace_formatted: string;
  status: string;
  bib?: number | string | null;
  rating_points?: number | null;
  rating_reason?: string | null;
  rating_breakdown?: Record<string, unknown> | null;
}

export interface PersonalBestItem {
  norm_distance: string;
  distance_title: string;
  time_s: number;
  time_formatted: string;
  pace_formatted: string;
  event_title: string;
  event_date?: string | null;
}

export interface AthleteRating {
  status: string;
  message: string;
  points?: number | null;
  rank?: number | null;
  starts_count: number;
  period_start?: string | null;
  period_end?: string | null;
}

export interface DynamicsPoint {
  date: string;
  event_title: string;
  norm_distance?: string | null;
  distance_name: string;
  time_s: number;
  time_formatted: string;
  pace_formatted: string;
  pace_s_per_km?: number | null;
}

export interface AthleteSummary {
  athlete: AthleteCandidate;
  total_starts: number;
  personal_bests: PersonalBestItem[];
  dynamics: DynamicsPoint[];
  rating: AthleteRating;
  has_cached_assessment: boolean;
}

export interface Assessment {
  athlete_id: number;
  athlete_name: string;
  assessment_text: string;
  metrics: Record<string, unknown>;
  model: string;
  cached: boolean;
  disclaimer: string;
}

export interface RaceItem {
  id: number;
  name_raw: string;
  norm_distance?: string | null;
  distance_m?: number | null;
  distance_km_raw?: number | null;
  total_count?: number | null;
}

export interface EventItem {
  id: number;
  source_id: number;
  source_name: string;
  title: string;
  date_begin?: string | null;
  date_end?: string | null;
  place?: string | null;
  address?: string | null;
  races: RaceItem[];
}

export interface RaceProtocolItem {
  result_id: number;
  athlete_id?: number | null;
  bib?: number | string | null;
  full_name_raw: string;
  gender?: string | null;
  age?: number | null;
  birth_year?: number | null;
  club_raw?: string | null;
  place_abs?: number | null;
  place_gender?: number | null;
  chip_time_s?: number | null;
  gun_time_s?: number | null;
  official_time_s?: number | null;
  time_formatted: string;
  pace_formatted: string;
  status: string | null;
}

export interface DistributionBin {
  bin_start_s: number;
  bin_end_s: number;
  label: string;
  count: number;
}

export interface CompetitionAthleteResult {
  time_s?: number | null;
  place_abs?: number | string | null;
  top_percent?: number | null;
  time_formatted?: string;
  pace_formatted?: string;
  [key: string]: unknown;
}

export interface CompetitionDistribution {
  race_id: number;
  race_name: string;
  norm_distance?: string | null;
  distance_m?: number | null;
  total_finishers: number;
  min_time_s: number;
  max_time_s: number;
  median_time_s: number;
  p25_time_s: number;
  p75_time_s: number;
  distribution_bins: DistributionBin[];
  athlete_result?: CompetitionAthleteResult | null;
}

export interface RaceInfo {
  id: number;
  event_id: number;
  name_raw: string;
  norm_distance?: string | null;
  distance_m?: number | null;
}

export interface RaceRatingLeader {
  athlete_id: number;
  result_id: number;
  full_name_raw: string;
  rating_rank: number;
  rating_points: number;
  rating_starts: number;
}

export interface RacePage {
  race: RaceInfo;
  event: EventItem | null;
  results: RaceProtocolItem[];
  pinned_athlete_result: RaceProtocolItem | null;
  competition: CompetitionDistribution | null;
  rating_leaders: RaceRatingLeader[];
}

export interface RatingRow {
  rank: number;
  athlete_id: number;
  display_name: string;
  birth_year?: number | null;
  gender?: string | null;
  points: number;
  best_points?: number | null;
  starts_count: number;
  rank_delta?: number | null;
}

export interface RatingPage {
  period_start?: string | null;
  period_end?: string | null;
  rows: RatingRow[];
  total: number;
  me_row: RatingRow | null;
}

export interface RatingNorm {
  distance_class: string;
  gender: string;
  value: number;
  unit: string;
}

export interface RatingFormula {
  year: number;
  norms: RatingNorm[];
  period_start?: string | null;
  period_end?: string | null;
}

export interface AgentRun {
  run_id: number;
  model?: string | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  seconds?: number | string | null;
  [key: string]: unknown;
}

export interface AgentReviewDecision {
  decision: string;
  author: string;
  comment?: string | null;
  decided_at: string;
  applied_result?: string | null;
  pr_url?: string | null;
}

export interface AgentReviewItem {
  issue_id: number;
  source?: string | null;
  stage?: string | null;
  kind?: string | null;
  object_ref: string;
  details: string;
  status: string;
  assignee?: string | null;
  run?: AgentRun | null;
  reason?: string | null;
  diff: string;
  report_text: string;
  reviews: AgentReviewDecision[];
}

export interface AgentReviewPage {
  items: AgentReviewItem[];
  sources: string[];
  statuses: string[];
  status: string;
  source: string;
  default_author: string;
  db_error: string | null;
}

export interface AgentApplyResult {
  result: string;
  status: string;
  pr_url?: string | null;
}

export interface AccessRequestItem {
  id: number;
  username: string;
  email: string;
  role: string;
  status: string;
  first_name: string;
  last_name: string;
  middle_name?: string | null;
  birth_date?: string | null;
  city?: string | null;
  athlete_id?: number | null;
  candidate_athlete_id?: number | null;
  candidate_athlete_name?: string | null;
  created_at?: string | null;
}

export interface AccessRequestDecisionPayload {
  decision: 'approve' | 'reject';
  athlete_id?: number | null;
  comment?: string | null;
}

export interface ReportItem {
  id: number;
  kind: string;
  user_id: number;
  athlete_id?: number | null;
  result_id?: number | null;
  event_id?: number | null;
  url?: string | null;
  message: string;
  status: string;
  decided_by?: string | null;
  decided_at?: string | null;
  moderator_comment?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ReportDecisionPayload {
  decision: 'accepted' | 'resolved' | 'rejected';
  moderator_comment?: string | null;
}
