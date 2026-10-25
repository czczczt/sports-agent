"""Единая схема результата (черновик v0)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["FIN", "DNS", "DNF", "DSQ", "LAP"]


class Race(BaseModel):
    race_id: str                      # id гонки на biathlonrus.com (/sorevnovaniya/races/<id>/)
    season: str                       # "2025-2026"
    competition: str                  # заголовок протокола, напр. "КУБОК РОССИИ ПО БИАТЛОНУ, 3 ЭТАП"
    discipline_raw: str               # "СПРИНТ 10 КМ МУЖЧИНЫ"
    discipline: Optional[str] = None  # sprint / pursuit / individual / mass_start / relay / ...
    gender: Optional[Literal["M", "F"]] = None
    distance_km: Optional[float] = None
    race_date: Optional[date] = None
    location: Optional[str] = None
    source_url: str
    protocol_status: Optional[str] = None  # "Окончательные результаты" / "Неофициальные ..."


class Result(BaseModel):
    race_id: str
    status: Status
    place: Optional[int] = None
    bib: int
    last_name: Optional[str] = None        # None, если ФИО в PDF нарисовано картинкой
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    name_missing: bool = False             # ФИО не извлечено из протокола
    name_source: Optional[str] = "protocol"  # protocol / sbr_base (восстановлено по базе СБР)
    sbr_code: Optional[str] = None         # код СБР, если сопоставлен с базой
    region_code: Optional[str] = None      # 3-буквенный код региона из протокола (ТЮМ, СВЕ, ...)
    birth_date: Optional[date] = None
    birth_year: Optional[int] = None       # в летних протоколах дата рождения дана только годом
    sport_rank: Optional[str] = None       # спортивный разряд до старта (МС, КМС, 1 разряд, ...)
    shooting: list[int] = Field(default_factory=list)  # промахи по рубежам
    misses_total: Optional[int] = None
    time_s: Optional[float] = None         # итоговое время, секунды
    behind_s: Optional[float] = None       # отставание от лидера, секунды
    ski_time_s: Optional[float] = None     # ходовое время (есть в индивидуальной гонке)
    points_raw: Optional[str] = None       # как в протоколе: "150", "-", "64/64", "56,5/-", "150 80"
    affiliation: Optional[str] = None      # строка "регион, город, школа, общество"
