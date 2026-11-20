from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class EventItem(BaseModel):
    id: int
    source_id: int
    source_name: str
    title: str
    date_begin: str | None = None
    date_end: str | None = None
    place: str | None = None
    address: str | None = None
    races: list[RaceItem] = []


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


class DistributionBin(BaseModel):
    bin_start_s: float
    bin_end_s: float
    label: str
    count: int


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
    athlete_result: dict[str, Any] | None = None


class UserOut(BaseModel):
    id: int | None = None
    username: str
    role: str
    status: str | None = "active"
    display_name: str
    athlete_id: int | None = None


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
    comment: str | None = None
