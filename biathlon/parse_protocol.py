"""Парсер итогового протокола СБР (PDF, генерируется ПО хронометража WSRP).

Протокол текстовый, поэтому берём текст через pdfplumber и разбираем построчно:
  строка спортсмена:  "1 36 ЛОГИНОВ Александр Викторович ТЮМ 31.01.1992 МСМК 0 0 0 22:03.3 150 МС"
  следующая строка:   "Тюменская область, г. Тюмень, ГАУ ТО "ЦСП", ЦСКА"   (принадлежность)
  секции статусов:    "Не стартовали" / "Не финишировали" / "Дисквалифицированы" / "Обгон на круг"
  подвал:             "ВСЕГО ФИН НС НФ ДСКВ КРУГ" + строка с числами — используем как контрольные суммы.

Колонки справа от даты рождения разбираем по шапке таблицы, т.к. в разных дисциплинах
число огневых рубежей разное (спринт: Л C, гонка преследования/масстарт: Л Л C C, ...).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pdfplumber

from schema import Race, Result

MONTHS = {"ЯНВ": 1, "ФЕВ": 2, "МАР": 3, "АПР": 4, "МАЙ": 5, "МАЯ": 5, "ИЮН": 6,
          "ИЮЛ": 7, "АВГ": 8, "СЕН": 9, "ОКТ": 10, "НОЯ": 11, "ДЕК": 12}
# WSRP пишет "Не стартовали", Ski123 (SIWIDATA) — "Не стартовало"
STATUS_SECTIONS = {"не стартовали": "DNS", "не стартовало": "DNS",
                   "не финишировали": "DNF", "не финишировало": "DNF", "сошли": "DNF",
                   "дисквалифицированы": "DSQ", "дисквалифицировано": "DSQ",
                   "обгон на круг": "LAP", "обогнаны на круг": "LAP"}
DISCIPLINES = [("гонка преследования", "pursuit"), ("преследован", "pursuit"),
               ("индивидуальн", "individual"), ("масстарт", "mass_start"), ("масс-старт", "mass_start"),
               ("суперспринт", "super_sprint"), ("спринт", "sprint"),
               ("смешанная эстафета", "mixed_relay"), ("сингл", "single_mixed_relay"),
               ("эстафета", "relay"), ("командн", "team"), ("патрульн", "patrol"),
               ("гонка", "individual")]  # "Гонка 12,5 км" = индивидуальная; проверяется последней

DOB = r"\d{2}\.\d{2}\.\d{4}"
BIRTH = rf"(?:{DOB}|(?:19|20)\d{{2}})"  # в летних протоколах вместо даты рождения только год
TIME = r"\d{1,2}(?::\d{2}){1,2}(?:[.,]\d)?"
# место, номер, [ФИО] [рег.код], дата/год рождения, всё остальное.
# ФИО и код региона бывают пустыми: в части PDF (doPDF) они нарисованы картинкой, а в юношеских
# протоколах вместо региона бывает код клуба (АНО, СИБ, ...). Разбор "ФИО/регион" — в split_ident.
RESULT_RE = re.compile(rf"^(\d+)\s+(\d+)\s+(.*?)\s*(?<!\S)({BIRTH})\s+(.*)$")
# в секциях статусов места нет: номер, [ФИО] [рег.код], дата, остальное
STATUS_RE = re.compile(rf"^(\d+)\s+(.*?)\s*(?<!\S)({BIRTH})(?:\s+(.*))?$")
RANK_WORDS = ("разряд", "разр.", "юн", "юн.", "юношеский", "юр")
HAS_LOWER = re.compile(r"[а-яё]")
REGION_RE = re.compile(r"[А-ЯЁ]{2,4}")
SKIP_PREFIXES = ("Данные получены", "Место Ст.№", "рождения", "Дата Вып", "===== PAGE")


@dataclass
class ParsedProtocol:
    race: Race
    results: list[Result]
    footer_counts: dict[str, int] = field(default_factory=dict)  # ВСЕГО/ФИН/НС/НФ/ДСКВ/КРУГ из подвала
    unparsed_lines: list[str] = field(default_factory=list)      # строки, похожие на результат, но не разобранные
    shooting_cols: int = 0

    def checks(self) -> dict[str, bool]:
        """Самопроверка по подвалу протокола."""
        by = lambda s: sum(r.status == s for r in self.results)
        fc, out = self.footer_counts, {}
        mapping = {"ФИН": "FIN", "НС": "DNS", "НФ": "DNF", "ДСКВ": "DSQ", "КРУГ": "LAP"}
        for k, st in mapping.items():
            if k in fc:
                out[k] = fc[k] == by(st)
        if "ВСЕГО" in fc:
            out["ВСЕГО"] = fc["ВСЕГО"] == len(self.results)
        fin = [r for r in self.results if r.status == "FIN"]
        places = [r.place for r in fin]
        out["места_по_порядку"] = places == sorted(places) and (not places or places[0] == 1)
        # подвал проверяет только число строк; поля проверяем отдельно
        times = [r.time_s for r in fin]
        out["время_у_всех_финишёров"] = bool(fin) and all(t is not None for t in times)
        out["время_растёт_с_местом"] = out["время_у_всех_финишёров"] and times == sorted(times)
        shot = [r for r in fin if r.shooting]
        if shot:
            # число рубежей одинаково у всех финишёров, а сумма промахов сходится со столбцом "Сум"
            out["стрельба_сходится"] = len({len(r.shooting) for r in shot}) == 1 and \
                all(sum(r.shooting) == r.misses_total for r in shot)
        return out


def to_seconds(t: str | None) -> float | None:
    if not t:
        return None
    t = t.lstrip("+").replace(",", ".")
    parts = [float(p) for p in t.split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def normalize_line(s: str) -> str:
    """Чинит артефакты извлечения текста.
    - разрядка (шрифт с межбуквенным интервалом в Ski123): "2 р а з р я д" -> "2 разряд";
    - склейки: "Александровна20.07.2012" -> "Александровна 20.07.2012", "15ГАЛИМЖАНОВ" -> "15 ГАЛИМЖАНОВ".
    Применяется только к строкам данных: в шапке одиночные буквы "Л Л C C" — это колонки."""
    s = re.sub(r"(?<!\S)((?:[А-Яа-яЁё] ){2,}[А-Яа-яЁё])(?!\S)", lambda m: m.group(1).replace(" ", ""), s)
    s = re.sub(rf"([А-Яа-яЁё])({DOB})", r"\1 \2", s)
    s = re.sub(r"(?<!\S)(\d+)([А-ЯЁ]{2,})", r"\1 \2", s)
    return s


def split_ident(raw: str) -> dict | None:
    """'ЛОГИНОВ Александр Викторович ТЮМ' -> ФИО + код региона.
    'ВЛГ' или '' -> ФИО не извлечено (нарисовано картинкой), код региона если есть.
    None -> мусор, строку не считаем результатом."""
    toks = raw.split()
    region = None
    if toks and REGION_RE.fullmatch(toks[-1]) and (len(toks) == 1 or HAS_LOWER.search(" ".join(toks[:-1]))):
        region = toks.pop()
    if not toks:
        return {"last_name": None, "first_name": None, "middle_name": None,
                "region_code": region, "name_missing": True}
    name = " ".join(toks)
    if not HAS_LOWER.search(name):
        return None
    last, first, middle = split_name(name)
    return {"last_name": last, "first_name": first, "middle_name": middle,
            "region_code": region, "name_missing": False}


def split_name(raw: str) -> tuple[str, str, str | None]:
    """'ХАЛИЛИ Саид Каримулла Саид Вахидулла' -> фамилия = ведущие слова КАПСОМ."""
    toks = raw.split()
    i = 0
    while i < len(toks) and toks[i].replace("-", "").isupper():
        i += 1
    i = max(i, 1)
    last = " ".join(toks[:i])
    first = toks[i] if i < len(toks) else ""
    middle = " ".join(toks[i + 1:]) or None
    return last, first, middle


def parse_tail(rest: str) -> dict:
    """Разбор правой части строки (после даты рождения).

    Шапке таблицы доверять нельзя: в индивидуальной гонке перед стрельбой стоит ходовое время,
    у чемпионата России две колонки очков, у обогнанных на круг вместо времени "КРУГ".
    Поэтому якорь — последнее значение времени (или "КРУГ"):
        [разряд] [ходовое время] [промахи по рубежам] [сумма промахов] ВРЕМЯ|КРУГ [+отставание] [очки…] [вып. разряд]
    """
    toks = rest.split()
    out: dict = {}
    if toks and re.search(r"[А-Яа-яЁё]", toks[-1]) and toks[-1] != "КРУГ":
        out["rank_after"] = toks.pop()
        if out["rank_after"] in RANK_WORDS and toks and toks[-1].isdigit():  # "2 разряд"
            out["rank_after"] = toks.pop() + " " + out["rank_after"]
    idx = next((i for i in range(len(toks) - 1, -1, -1)
                if re.fullmatch(TIME, toks[i]) or toks[i] == "КРУГ"), None)
    if idx is None:
        out["sport_rank"] = " ".join(toks) or None
        return out
    after, before = toks[idx + 1:], toks[:idx]
    if toks[idx] == "КРУГ":
        out["lapped"] = True
    else:
        out["time"] = toks[idx]
        if after and after[0].startswith("+"):
            out["behind"] = after.pop(0)
    out["points_raw"] = " ".join(after) or None
    if before and before[-1].isdigit():
        out["misses_total"] = int(before.pop())
        # число рубежей берём из данных, а не из шапки (шапка "Л C Л C" при трёх рубежах у 13-14 лет);
        # промахи на рубеже — одна цифра (0..5), это отделяет их от "2" в "2 разряд"
        shots = []
        while before and len(before[-1]) == 1 and before[-1].isdigit():
            shots.insert(0, int(before.pop()))
        out["shooting"] = shots
    # ходовое время (индивидуальная гонка; в летних протоколах — перед разрядом)
    ti = next((i for i, t in enumerate(before) if re.fullmatch(TIME, t)), None)
    if ti is not None:
        out["ski_time"] = before.pop(ti)
    out["sport_rank"] = " ".join(before) or None
    return out


def _header_meta(lines: list[str]) -> dict:
    meta: dict = {"competition": lines[0].strip() if lines else ""}
    for ln in lines[:12]:
        m = re.search(r"\b(\d{1,2}) ([А-Я]{3}) (\d{4})\b", ln)
        if m and "race_date" not in meta and m.group(2) in MONTHS:
            meta["race_date"] = date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
            meta["location"] = ln[: m.start()].rsplit(" ", 2)[0].strip()
        low = ln.lower()
        if "discipline_raw" not in meta and re.search(r"\d+(?:[,.]\d+)?\s*(км|x|х)", low) and \
                any(k in low for k, _ in DISCIPLINES):
            meta["discipline_raw"] = ln.strip()
        if "результат" in low and "protocol_status" not in meta:
            meta["protocol_status"] = ln.strip()
    raw = meta.get("discipline_raw", "").lower()
    meta["discipline"] = next((v for k, v in DISCIPLINES if k in raw), None)
    meta["gender"] = "M" if "мужчин" in raw or "юноши" in raw or "юниоры" in raw else \
        "F" if "женщин" in raw or "девушки" in raw or "юниорки" in raw else None
    d = re.search(r"(\d+(?:[,.]\d+)?)\s*км", raw)
    meta["distance_km"] = float(d.group(1).replace(",", ".")) if d else None
    return meta


def parse_pdf(path: Path, race_id: str, season: str, source_url: str) -> ParsedProtocol:
    with pdfplumber.open(path) as pdf:
        pages = [(p.extract_text() or "").splitlines() for p in pdf.pages]
    first = pages[0] if pages else []
    meta = _header_meta(first)
    race = Race(race_id=race_id, season=season, source_url=source_url,
                competition=meta.get("competition", ""), discipline_raw=meta.get("discipline_raw", ""),
                discipline=meta.get("discipline"), gender=meta.get("gender"),
                distance_km=meta.get("distance_km"), race_date=meta.get("race_date"),
                location=meta.get("location"), protocol_status=meta.get("protocol_status"))

    n_shoot = 0
    for ln in first:
        if ln.startswith("Место"):
            n_shoot = sum(t in ("Л", "С", "C") for t in ln.split())  # число огневых рубежей
            break

    parsed = ParsedProtocol(race=race, results=[], shooting_cols=n_shoot)
    status = "FIN"
    for lines in pages:
        last: Result | None = None
        for i, ln in enumerate(lines):
            s = ln.strip()
            low = s.lower().rstrip(":").strip()
            if low in STATUS_SECTIONS:
                status, last = STATUS_SECTIONS[low], None
                continue
            if s.startswith("ВСЕГО") or " ВСЕГО ФИН" in s:
                hdr = s.split()[s.split().index("ВСЕГО"):]
                # значения — последние токены следующей строки; Ski123 пишет "-" вместо 0
                vals = lines[i + 1].split()[-len(hdr):] if i + 1 < len(lines) else []
                if len(vals) == len(hdr) and all(v.isdigit() or v == "-" for v in vals):
                    parsed.footer_counts = {h: int(v) if v.isdigit() else 0 for h, v in zip(hdr, vals)}
                last = None
                continue
            if s.startswith(SKIP_PREFIXES):
                last = None
                continue
            s = normalize_line(s)
            m = RESULT_RE.match(s) if status == "FIN" else None
            if m and (ident := split_ident(m.group(3))) is not None:
                place, bib, _, dob, rest = m.groups()
                tail = parse_tail(rest)
                # обогнанные на круг получают место, но в подвале считаются как КРУГ, а не ФИН
                st = "LAP" if tail.get("lapped") else "FIN"
                last = Result(race_id=race_id, status=st, place=int(place), bib=int(bib), **ident,
                              birth_date=_dob(dob), birth_year=int(dob[-4:]), sport_rank=tail.get("sport_rank"),
                              shooting=tail.get("shooting", []), misses_total=tail.get("misses_total"),
                              time_s=to_seconds(tail.get("time")), behind_s=to_seconds(tail.get("behind")),
                              ski_time_s=to_seconds(tail.get("ski_time")), points_raw=tail.get("points_raw"))
                parsed.results.append(last)
                continue
            m = STATUS_RE.match(s) if status != "FIN" else None
            if m and (ident := split_ident(m.group(2))) is not None:
                bib, _, dob, rest = m.groups()
                last = Result(race_id=race_id, status=status, bib=int(bib), **ident,
                              birth_date=_dob(dob), birth_year=int(dob[-4:]), sport_rank=rest or None)
                parsed.results.append(last)
                continue
            if last is not None and last.affiliation is None and "," in s:
                last.affiliation = s
                last = None
                continue
            if re.search(DOB, s) and re.match(r"^\d+\s", s):
                parsed.unparsed_lines.append(s)
            last = None
    _fix_rank_digit_in_shooting(parsed.results)
    return parsed


def _fix_rank_digit_in_shooting(results: list[Result]) -> None:
    """Разряд бывает записан голой цифрой ("1" = 1 разряд) и тогда попадает в промахи:
    "1 2 1 3" -> рубежи [1,2,1], сумма 3. Если у строки рубежей больше, чем у большинства
    в гонке, и без лишних ведущих цифр сумма сходится — переносим их в разряд."""
    lens = Counter(len(r.shooting) for r in results if r.shooting)
    if not lens:
        return
    n = lens.most_common(1)[0][0]
    for r in results:
        extra = len(r.shooting) - n
        if extra > 0 and sum(r.shooting[extra:]) == r.misses_total:
            moved = " ".join(map(str, r.shooting[:extra]))
            r.sport_rank = f"{moved} {r.sport_rank}".strip() if r.sport_rank else moved
            r.shooting = r.shooting[extra:]


def _dob(s: str) -> date | None:
    if "." not in s:  # только год рождения
        return None
    d, m, y = map(int, s.split("."))
    try:
        return date(y, m, d)
    except ValueError:
        return None
