from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator
from typing_extensions import NotRequired, TypedDict


class AthleteCandidate(BaseModel):
    id: int
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    birth_date: str | None = None
    birth_year: int | None = None
    gender: str | None = None
    city: str | None = None
    region: str | None = None
    club: str | None = None
    employee_status: str | None = "presumed"
    employee_since: str | None = None
    employee_until: str | None = None
    is_hidden: bool = False
    starts_count: int = 0
    results_count: int = 0


class AthleteResultItem(BaseModel):
    result_id: int
    event_id: int
    event_title: str
    event_date: str | None = None
    source_name: str
    race_id: int
    distance_name: str
    norm_distance: str | None = None
    distance_m: int | None = None
    place_abs: int | str | None = None
    place_gender: int | str | None = None
    total_finishers: int | None = None
    total_participants: int | None = None
    chip_time_s: float | None = None
    gun_time_s: float | None = None
    time_formatted: str
    pace_formatted: str
    status: str
    points: float | None = None
    bib: int | str | None = None
    rating_points: float | None = None
    rating_reason: str | None = None
    rating_breakdown: dict[str, Any] | None = None


class PersonalBestItem(BaseModel):
    norm_distance: str
    distance_title: str
    time_s: float
    time_formatted: str
    pace_formatted: str
    event_title: str
    event_date: str | None = None


class RatingPlaceholder(BaseModel):
    status: str = "counted"
    message: str = "Рейтинг за последние 365 дней"
    points: float | None = None
    rank: int | None = None
    starts_count: int = 0
    period_start: str | None = None
    period_end: str | None = None


class DynamicsPoint(BaseModel):
    date: str
    event_title: str
    norm_distance: str | None = None
    distance_name: str
    time_s: float
    time_formatted: str
    pace_formatted: str
    pace_s_per_km: float | None = None


class AthleteSummaryResponse(BaseModel):
    athlete: AthleteCandidate
    total_starts: int
    personal_bests: list[PersonalBestItem]
    dynamics: list[DynamicsPoint]
    rating: RatingPlaceholder
    has_cached_assessment: bool = False


class AssessmentResponse(BaseModel):
    athlete_id: int
    athlete_name: str
    assessment_text: str
    metrics: dict[str, Any]
    model: str
    cached: bool
    disclaimer: str = "Оценка носит исключительно справочный характер."


class RaceItem(BaseModel):
    id: int
    name_raw: str
    norm_distance: str | None = None
    distance_m: int | None = None
    distance_km_raw: float | None = None
    total_count: int | None = None


class PastEditionDistanceCount(BaseModel):
    distance_name: str
    count: int


class PastEditionStats(BaseModel):
    edition_year: int | None = None
    edition_title: str | None = None
    employees_total: int = 0
    distance_counts: list[PastEditionDistanceCount] = Field(default_factory=list)


class EventItem(BaseModel):
    id: int
    source_id: int
    source_name: str
    title: str
    date_begin: str | None = None
    date_end: str | None = None
    place: str | None = None
    address: str | None = None
    status: str = "done"
    sport: str = "run"
    series_id: int | None = None
    series_name: str | None = None
    possible_duplicate_id: int | None = None
    past_edition: PastEditionStats | None = None
    races: list[RaceItem] = []


class EventSeriesItem(BaseModel):
    id: int
    name: str
    name_norm: str
    city: str | None = None
    sport: str = "run"
    events_count: int = 0


class PlannedDistanceCreate(BaseModel):
    name: str
    distance_m: int | None = None
    distance_km: float | None = None


class PlannedEventCreate(BaseModel):
    title: str
    sport: str = "run"
    city: str | None = None
    address: str | None = None
    planned_date_start: str
    planned_date_end: str | None = None
    planned_note: str | None = None
    series_id: int | None = None
    races: list[PlannedDistanceCreate] = Field(default_factory=list)


class SeriesSuggestItem(BaseModel):
    series_id: int
    series_name: str
    city: str | None = None
    sport: str = "run"
    similarity: float = 1.0


class EventDuplicateCandidate(BaseModel):
    event_id: int
    title: str
    date_begin: str | None = None
    place: str | None = None
    status: str
    similarity_reason: str


class EventMergeRequest(BaseModel):
    planned_event_id: int
    actual_event_id: int


class EventSeriesAttachRequest(BaseModel):
    series_id: int


class RaceProtocolItem(BaseModel):
    result_id: int
    athlete_id: int | None = None
    bib: int | str | None = None
    full_name_raw: str
    gender: str | None = None
    age: int | None = None
    birth_year: int | None = None
    club_raw: str | None = None
    place_abs: int | None = None
    place_gender: int | None = None
    chip_time_s: float | None = None
    gun_time_s: float | None = None
    time_formatted: str
    pace_formatted: str
    status: str
    points: float | None = None


class DistributionBin(BaseModel):
    bin_start_s: float
    bin_end_s: float
    label: str
    count: int


class CompetitionAthleteResult(TypedDict):
    result_id: int
    time_s: float
    place_abs: int | str | None
    percentile: NotRequired[float | None]
    top_percent: NotRequired[float | None]
    time_formatted: str | None
    pace_formatted: str | None
    status: str | None
    summary_text: NotRequired[str]


class CompetitionDistribution(BaseModel):
    race_id: int
    race_name: str
    norm_distance: str | None = None
    distance_m: int | None = None
    total_finishers: int
    min_time_s: float
    max_time_s: float
    median_time_s: float
    p25_time_s: float
    p75_time_s: float
    distribution_bins: list[DistributionBin]
    athlete_result: CompetitionAthleteResult | None = None


class UserOut(BaseModel):
    id: int | None = None
    username: str
    role: str
    status: str | None = "active"
    display_name: str
    athlete_id: int | None = None
    captain_sports: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RatingRow(BaseModel):
    rank: int
    athlete_id: int
    display_name: str
    birth_year: int | None = None
    gender: str | None = None
    points: float
    best_points: float | None = None
    starts_count: int = 0
    rank_delta: int | None = None


class RatingPageResponse(BaseModel):
    version_id: int | None = None
    published_at: datetime | None = None
    sport: str = "run"
    as_of: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    rows: list[RatingRow]
    total: int
    me_row: RatingRow | None = None


class RatingNorm(BaseModel):
    distance_class: str
    gender: str
    value: float
    unit: str


class RunNormItem(BaseModel):
    year: int
    distance_class: str
    gender: str
    value: float
    unit: str


class RlPointsItem(BaseModel):
    athlete_id: int
    rl_season: str
    points: float
    details: dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime | None = None


class RatingFormulaResponse(BaseModel):
    year: int
    norms: list[RatingNorm]
    period_start: str | None = None
    period_end: str | None = None


class RaceInfo(BaseModel):
    id: int
    event_id: int
    name_raw: str
    norm_distance: str | None = None
    distance_m: int | None = None


class RaceRatingLeader(BaseModel):
    athlete_id: int
    result_id: int
    full_name_raw: str
    rating_rank: int
    rating_points: float
    rating_starts: int
    place_abs: int | None = None
    chip_time_s: float | None = None
    gun_time_s: float | None = None


class RacePageResponse(BaseModel):
    race: RaceInfo
    event: EventItem | None = None
    results: list[RaceProtocolItem]
    pinned_athlete_result: RaceProtocolItem | None = None
    competition: CompetitionDistribution | None = None
    rating_leaders: list[RaceRatingLeader] = []
    sber_finishers_count: int | None = None


class ReportCreateRequest(BaseModel):
    kind: str
    athlete_id: int | None = None
    result_id: int | None = None
    event_id: int | None = None
    url: str | None = None
    message: str


class ReportDecisionRequest(BaseModel):
    decision: str
    moderator_comment: str | None = None


class ReportOut(BaseModel):
    id: int
    kind: str
    user_id: int | None = None
    athlete_id: int | None = None
    result_id: int | None = None
    event_id: int | None = None
    url: str | None = None
    message: str | None = None
    status: str
    decided_by: str | None = None
    decided_at: str | None = None
    moderator_comment: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = None
    birth_date: str | None = None
    city: str | None = None
    consent: bool = Field(
        ..., description="Согласие на обработку персональных данных (обязательно True)"
    )
    consent_version: str | None = "v1.0"

    @field_validator("consent")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "Регистрация без согласия на обработку персональных данных отклоняется"
            )
        return v


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=6)


class AccessRequestOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str
    status: str
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    birth_date: str | None = None
    city: str | None = None
    athlete_id: int | None = None
    candidate_athlete_id: int | None = None
    candidate_athlete_name: str | None = None
    created_at: str | None = None


class AccessRequestDecision(BaseModel):
    decision: str
    athlete_id: int | None = None
    create_athlete: bool | None = None
    comment: str | None = None


class AdminAthleteDetail(BaseModel):
    id: int
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    birth_date: str | None = None
    birth_year: int | None = None
    gender: str | None = None
    city: str | None = None
    club: str | None = None
    employee_status: str | None = "presumed"
    employee_since: str | None = None
    employee_until: str | None = None
    is_hidden: bool = False
    starts_count: int = 0
    results_count: int = 0
    linked_user_id: int | None = None
    linked_username: str | None = None


class AdminAthleteCreate(BaseModel):
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: str | None = None
    birth_year: int | None = None
    gender: str | None = None
    city: str | None = None
    club: str | None = None
    employee_status: str = "presumed"
    employee_since: str | None = None
    employee_until: str | None = None
    is_hidden: bool = False


class AdminAthleteUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    birth_date: str | None = None
    birth_year: int | None = None
    gender: str | None = None
    city: str | None = None
    club: str | None = None
    employee_status: str | None = None
    employee_since: str | None = None
    employee_until: str | None = None
    is_hidden: bool | None = None


class RosterImportResult(BaseModel):
    total: int
    created: int
    updated: int
    errors: list[str] = []


class VerifyQueueItem(BaseModel):
    athlete_id: int
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    birth_year: int | None = None
    sport: str = "run"
    rank: int
    points: float
    starts_count: int = 0
    employee_status: str | None = "presumed"
    linked_user_id: int | None = None
    linked_username: str | None = None
    linked_user_email: str | None = None


class VerifyQueueDecision(BaseModel):
    status: str = Field(..., pattern="^(confirmed|not_employee)$")
    comment: str | None = None


class VerifyQueueDecisionResponse(BaseModel):
    success: bool
    athlete_id: int
    new_status: str
    auto_blocked_user: bool = False
    message: str


# --- Block 4: Captain & Admin Management Models (SPEC v1.3 §2, §3.2, §3.5, §5, §11) ---


class AdminRaceUpdate(BaseModel):
    scoring_class: str | None = None
    distance_class_override: str | None = None
    elevation_gain_m: float | None = None
    is_rl_series: bool | None = None
    sport: str | None = None
    special: str | None = None


class AdminRaceDetail(BaseModel):
    id: int
    competition_id: int
    name: str | None = None
    sport: str | None = None
    scoring_class: str | None = None
    distance_class_override: str | None = None
    distance_m: int | None = None
    distance_km_raw: float | None = None
    elevation_gain_m: float | None = None
    is_rl_series: bool = False
    special: str | None = "regular"
    total_count: int | None = 0


class ManualProtocolRow(BaseModel):
    bib: str | None = None
    full_name_raw: str
    gender: str | None = None
    birth_year: int | None = None
    birth_date: str | None = None
    club_raw: str | None = None
    status: str | None = "FIN"
    place_abs: int | None = None
    place_gender: int | None = None
    chip_time_s: float | None = None
    gun_time_s: float | None = None


class ManualProtocolUploadRequest(BaseModel):
    rows: list[ManualProtocolRow]


class ManualProtocolUploadResponse(BaseModel):
    success: bool
    race_id: int
    imported_count: int
    message: str


class DeleteProtocolResponse(BaseModel):
    success: bool
    race_id: int
    deleted_count: int
    message: str


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str
    status: str
    display_name: str | None = None
    athlete_id: int | None = None
    captain_sports: list[str] = Field(default_factory=list)
    created_at: str | None = None


class AdminUserUpdate(BaseModel):
    role: str | None = None
    status: str | None = None
    display_name: str | None = None
    athlete_id: int | None = None
    captain_sports: list[str] | None = None


class AdminSettingItem(BaseModel):
    key: str
    value: Any
    updated_at: str | None = None
    updated_by: int | None = None


class AdminSettingUpdate(BaseModel):
    key: str
    value: Any


class AdminSourceOut(BaseModel):
    id: int
    name: str
    base_url: str | None = None
    platform: str | None = None
    enabled: bool = True
    priority: int = 100
    sport_types: str | None = None


class AdminSourceUpdate(BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    sport_types: str | None = None
    base_url: str | None = None


class CaptainNotEmployeeItem(BaseModel):
    audit_id: int
    athlete_id: int
    athlete_name: str | None = None
    moderator_username: str
    old_status: str | None = None
    new_status: str = "not_employee"
    created_at: str
    comment: str | None = None


class AdminSummaryResponse(BaseModel):
    captain_not_employee_changes: list[CaptainNotEmployeeItem] = Field(default_factory=list)
    pending_access_requests_count: int = 0
    pending_reports_count: int = 0
    unverified_top_n_count: int = 0
    trails_without_elevation_count: int = 0
    failed_adapters_count: int = 0

