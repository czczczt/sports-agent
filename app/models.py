from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class AthleteCandidate(BaseModel):
    id: int
    display_name: str
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    club: Optional[str] = None
    starts_count: int = 0
    results_count: int = 0


class AthleteResultItem(BaseModel):
    result_id: int
    event_id: int
    event_title: str
    event_date: Optional[str] = None
    source_name: str
    race_id: int
    distance_name: str
    norm_distance: Optional[str] = None
    distance_m: Optional[int] = None
    place_abs: Optional[int] = None
    place_gender: Optional[int] = None
    chip_time_s: Optional[float] = None
    gun_time_s: Optional[float] = None
    time_formatted: str
    pace_formatted: str
    status: str
    bib: Optional[int] = None


class PersonalBestItem(BaseModel):
    norm_distance: str
    distance_title: str
    time_s: float
    time_formatted: str
    pace_formatted: str
    event_title: str
    event_date: Optional[str] = None


class RatingPlaceholder(BaseModel):
    status: str = "pending_curator_formula"
    message: str = "Формула рейтинга согласуется с куратором"
    points: Optional[float] = None
    rank: Optional[int] = None


class DynamicsPoint(BaseModel):
    date: str
    event_title: str
    norm_distance: Optional[str] = None
    distance_name: str
    time_s: float
    time_formatted: str
    pace_formatted: str
    pace_s_per_km: Optional[float] = None


class AthleteSummaryResponse(BaseModel):
    athlete: AthleteCandidate
    total_starts: int
    personal_bests: List[PersonalBestItem]
    dynamics: List[DynamicsPoint]
    rating: RatingPlaceholder
    has_cached_assessment: bool = False


class AssessmentResponse(BaseModel):
    athlete_id: int
    athlete_name: str
    assessment_text: str
    metrics: Dict[str, Any]
    model: str
    cached: bool
    disclaimer: str = "Оценка носит исключительно справочный характер."


class RaceItem(BaseModel):
    id: int
    name_raw: str
    norm_distance: Optional[str] = None
    distance_m: Optional[int] = None
    distance_km_raw: Optional[float] = None
    total_count: Optional[int] = None


class EventItem(BaseModel):
    id: int
    source_id: int
    source_name: str
    title: str
    date_begin: Optional[str] = None
    date_end: Optional[str] = None
    place: Optional[str] = None
    address: Optional[str] = None
    races: List[RaceItem] = []


class RaceProtocolItem(BaseModel):
    result_id: int
    athlete_id: Optional[int] = None
    bib: Optional[int] = None
    full_name_raw: str
    gender: Optional[str] = None
    age: Optional[int] = None
    birth_year: Optional[int] = None
    club_raw: Optional[str] = None
    place_abs: Optional[int] = None
    place_gender: Optional[int] = None
    chip_time_s: Optional[float] = None
    gun_time_s: Optional[float] = None
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
    norm_distance: Optional[str] = None
    distance_m: Optional[int] = None
    total_finishers: int
    min_time_s: float
    max_time_s: float
    median_time_s: float
    p25_time_s: float
    p75_time_s: float
    distribution_bins: List[DistributionBin]
    athlete_result: Optional[Dict[str, Any]] = None
