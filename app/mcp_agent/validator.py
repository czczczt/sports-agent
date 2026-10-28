"""
Модуль валидации и тестов качества спарсенных данных.
Проверяет строки протокола на:
1. Долю пустых значений (NULL) в обязательных полях (ФИО, время, места).
2. Соответствие общего количества строк заявленному числу участников.
3. Монотонность времени (время должно расти с местом для финишеров).
4. Корректность статусов участников (FIN, DNF, DSQ, DNS и др.).
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ValidationReport:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    null_ratios: Dict[str, float] = field(default_factory=dict)
    total_rows: int = 0
    fin_rows: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


def validate_protocol_data(
    rows: List[Dict[str, Any]],
    race_info: Optional[Dict[str, Any]] = None,
    max_null_name_ratio: float = 0.05,
    max_null_time_ratio: float = 0.05,
) -> ValidationReport:
    """
    Выполняет комплексную проверку спарсенных данных дистанции.
    Если проверка не пройдена (is_valid=False), требуется запуск ИИ-агента через MCP.
    """
    issues = []
    total = len(rows)
    if total == 0:
        return ValidationReport(
            is_valid=False,
            issues=["zero_rows: Спарсено 0 строк протокола (пустой ответ или сменилась разметка)."],
            total_rows=0
        )

    # 1. Проверка на долю NULL в критических полях
    null_names = sum(1 for r in rows if not r.get("full_name_raw") or str(r.get("full_name_raw")).strip() == "")
    
    # Для времени: хотя бы одно время (чистое chip или пистолетное gun) должно быть заполнено для статуса FIN
    fin_rows = [r for r in rows if r.get("status") == "FIN"]
    null_time_fin = sum(
        1 for r in fin_rows 
        if (r.get("chip_time_s") is None or r.get("chip_time_s") <= 0) and 
           (r.get("gun_time_s") is None or r.get("gun_time_s") <= 0)
    )

    null_place_fin = sum(
        1 for r in fin_rows 
        if r.get("place_abs") is None or r.get("place_abs") <= 0
    )

    name_null_ratio = null_names / total
    time_null_ratio = (null_time_fin / len(fin_rows)) if fin_rows else 0.0
    place_null_ratio = (null_place_fin / len(fin_rows)) if fin_rows else 0.0

    null_ratios = {
        "full_name_null_ratio": round(name_null_ratio, 4),
        "fin_time_null_ratio": round(time_null_ratio, 4),
        "fin_place_null_ratio": round(place_null_ratio, 4),
    }

    if name_null_ratio > max_null_name_ratio:
        issues.append(
            f"high_null_names: Доля пустых ФИО составляет {name_null_ratio * 100:.1f}% (порог {max_null_name_ratio * 100:.1f}%)."
        )

    if time_null_ratio > max_null_time_ratio:
        issues.append(
            f"high_null_times: У {time_null_ratio * 100:.1f}% финишеров отсутствует официальное время (порог {max_null_time_ratio * 100:.1f}%)."
        )

    if place_null_ratio > 0.10:
        issues.append(
            f"high_null_places: У {place_null_ratio * 100:.1f}% финишеров не проставлены абсолютные места."
        )

    # 2. Проверка заявленного количества участников
    if race_info and race_info.get("total_count"):
        declared = race_info["total_count"]
        # Допустимое расхождение не более 10%
        if declared > 0 and abs(total - declared) / declared > 0.10:
            issues.append(
                f"count_mismatch: Заявлено участников: {declared}, спарсено: {total} (расхождение > 10%)."
            )

    # 3. Проверка статусов участников
    valid_statuses = {"FIN", "DNF", "DSQ", "DNS", "NC", "LAP"}
    invalid_statuses = {
        r.get("status") for r in rows 
        if r.get("status") and r.get("status") not in valid_statuses
    }
    if invalid_statuses:
        issues.append(
            f"invalid_statuses: Обнаружены неизвестные статусы участников: {list(invalid_statuses)}."
        )

    # 4. Проверка монотонности времени финишеров (время должно расти с местом)
    sorted_fin = sorted([r for r in fin_rows if r.get("place_abs")], key=lambda x: x["place_abs"])
    monotonicity_violations = 0
    prev_time = 0.0

    for r in sorted_fin:
        t = r.get("chip_time_s") or r.get("gun_time_s")
        if t and t > 0:
            # Если следующее место финишировало значительно быстрее предыдущего (> 3 сек расхождения)
            if prev_time > 0 and t < prev_time - 3.0:
                monotonicity_violations += 1
            prev_time = max(prev_time, t)

    if len(sorted_fin) > 10 and monotonicity_violations > len(sorted_fin) * 0.05:
        issues.append(
            f"time_non_monotonic: Нарушение монотонности времени у {monotonicity_violations} участников (время уменьшается с ростом места)."
        )

    is_valid = len(issues) == 0

    return ValidationReport(
        is_valid=is_valid,
        issues=issues,
        null_ratios=null_ratios,
        total_rows=total,
        fin_rows=len(fin_rows),
        details={
            "monotonicity_violations": monotonicity_violations,
            "checked_fields": ["full_name_raw", "time", "place_abs", "status"]
        }
    )
