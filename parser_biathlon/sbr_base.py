"""Справочник спортсменов СБР (base.biathlonrus.com) и сопоставление с результатами.

Две задачи:
1. Привязать запись протокола к коду СБР по ФИО + дате рождения.
2. Восстановить ФИО у строк, где оно в PDF нарисовано картинкой (name_missing),
   по дате рождения + полу + коду региона. Принимаем только однозначный кандидат.

Точность восстановления оцениваем на строках, где ФИО известно: прячем его, восстанавливаем
и сравниваем с настоящим (evaluate_recovery).
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime

import pandas as pd

import sbr_crawler as cr

ATHLETES_URL = "http://base.biathlonrus.com/files/lists/Athlete.CSV"


def norm(s) -> str:
    return str(s).strip().upper().replace("Ё", "Е") if isinstance(s, str) and s.strip() else ""


def load_athletes() -> pd.DataFrame:
    raw = cr.fetch(ATHLETES_URL, binary=True).decode("cp1251")
    rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
    # в выгрузке колонки сдвинуты: "Фамилия Англ" на самом деле отчество
    df = pd.DataFrame(rows[1:], columns=rows[0]).rename(columns={
        "Код СБР": "sbr_code", "Фамилия": "last_name", "Имя": "first_name", "Фамилия Англ": "middle_name",
        "Пол": "sex", "Регион (3-х буквенное название)": "region_code", "Дата рождения": "birth_date"})
    df["sbr_code"] = df["sbr_code"].str.strip('="')   # Excel-формула ="112010200800"
    df["birth_date"] = pd.to_datetime(df["birth_date"], format="%d.%m.%Y", errors="coerce").dt.date
    df["gender"] = df["sex"].map({"М": "M", "Ж": "F"})
    return df[["sbr_code", "last_name", "first_name", "middle_name", "gender", "region_code", "birth_date"]]


class Matcher:
    def __init__(self, athletes: pd.DataFrame):
        self.by_name = {}
        self.by_dob = defaultdict(list)
        for a in athletes.itertuples(index=False):
            if a.birth_date is None or pd.isna(a.birth_date):
                continue
            self.by_name.setdefault((norm(a.last_name), norm(a.first_name), a.birth_date), []).append(a)
            self.by_dob[a.birth_date].append(a)

    def by_identity(self, last, first, dob):
        c = self.by_name.get((norm(last), norm(first), dob), [])
        return c[0] if len(c) == 1 else None

    def recover(self, dob, gender, region):
        c = [a for a in self.by_dob.get(dob, []) if (gender is None or a.gender == gender)
             and (not region or a.region_code == region)]
        return c[0] if len(c) == 1 else None


def _as_date(v):
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v), "%Y-%m-%d").date()
    except ValueError:
        return None


def enrich(results: pd.DataFrame, races: pd.DataFrame, m: Matcher) -> tuple[pd.DataFrame, dict]:
    df = results.merge(races[["race_id", "gender"]], on="race_id", how="left")
    df["birth_date"] = df["birth_date"].map(_as_date)
    stats = defaultdict(int)
    for i, r in df.iterrows():
        g = r["gender"] if isinstance(r["gender"], str) else None
        reg = r["region_code"] if isinstance(r["region_code"], str) else None
        if r["name_missing"]:
            stats["name_missing"] += 1
            a = m.recover(r["birth_date"], g, reg) if r["birth_date"] else None
            if a is not None:
                stats["recovered"] += 1
                df.loc[i, ["last_name", "first_name", "middle_name", "sbr_code", "name_source"]] = \
                    [a.last_name.upper(), a.first_name, a.middle_name, a.sbr_code, "sbr_base"]
        else:
            stats["named"] += 1
            a = m.by_identity(r["last_name"], r["first_name"], r["birth_date"])
            if a is not None:
                stats["linked_to_sbr"] += 1
                df.loc[i, "sbr_code"] = a.sbr_code
            if r["name_source"] == "ocr":
                # проверка OCR: ФИО + ДР совпали с базой — подтверждено; иначе смотрим, есть ли
                # в базе однозначный кандидат по ДР + полу + региону (тогда OCR, скорее всего, ошибся)
                stats["ocr"] += 1
                if a is not None:
                    stats["ocr_confirmed_by_sbr"] += 1
                    # длинное отчество в PDF визуально обрезано шириной колонки ("Александровн") —
                    # у подтверждённых базой берём отчество из базы
                    if a.middle_name and norm(a.middle_name) != norm(r["middle_name"]):
                        stats["ocr_middle_name_fixed"] += 1
                        df.loc[i, "middle_name"] = a.middle_name
                    df.loc[i, "name_source"] = "ocr+sbr"
                elif r["birth_date"] and m.recover(r["birth_date"], g, reg) is not None:
                    stats["ocr_conflicts_with_sbr"] += 1
                    df.loc[i, "name_source"] = "ocr_unverified"
    return df.drop(columns=["gender"]), dict(stats)


def evaluate_recovery(enriched: pd.DataFrame, races: pd.DataFrame, m: Matcher) -> dict:
    """Прячем ФИО у строк с известным кодом СБР и проверяем, верно ли его восстанавливаем."""
    df = enriched.merge(races[["race_id", "gender"]], on="race_id", how="left")
    df = df[df["sbr_code"].notna() & (df["name_source"] == "protocol")]
    out = {"with_region": [0, 0, 0], "without_region": [0, 0, 0]}  # [попыток, восстановлено, верно]
    for r in df.itertuples(index=False):
        g = r.gender if isinstance(r.gender, str) else None
        for key, reg in (("with_region", r.region_code if isinstance(r.region_code, str) else None),
                         ("without_region", None)):
            out[key][0] += 1
            a = m.recover(r.birth_date, g, reg)
            if a is not None:
                out[key][1] += 1
                out[key][2] += a.sbr_code == r.sbr_code
    return {k: {"попыток": n, "восстановлено": rec, "верно": ok,
                "coverage": round(rec / n, 3) if n else None,
                "precision": round(ok / rec, 3) if rec else None} for k, (n, rec, ok) in out.items()}
