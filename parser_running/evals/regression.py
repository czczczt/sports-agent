"""Регрессия: то, что уже работало, после правки агента должно работать по-прежнему."""
from normalize import infer_place_by, is_sber_club, km_from_name, km_to_m, norm_distance, ru_date, to_seconds


def run() -> tuple[bool, str]:
    cases = [
        (to_seconds("01:03:24"), 3804), (to_seconds("08:38"), 518), (to_seconds("0:39:25,52"), 2365.52),
        (to_seconds("DNF"), None), (to_seconds(""), None),
        (norm_distance(km_to_m(21.0975)), "half_marathon"), (norm_distance(km_to_m(10)), "10000m"),
        (norm_distance(km_to_m(15)), None), (norm_distance(km_to_m(1.609)), "1mile"),
        (km_from_name("10 км - любители"), 10.0), (km_from_name("21,1 км"), 21.1),
        (km_from_name("100 м (жен.)"), 0.1), (km_from_name("1 миля (муж.)"), 1.609), (km_from_name("4-5 лет"), None),
        (ru_date("26 сентября 2026, Москва"), "2026-09-26"), (ru_date("9 мая 2025"), "2025-05-09"),
        (is_sber_club("SBERRUN"), True), (is_sber_club("ПАО Сбербанк"), True), (is_sber_club(None, "sberufa"), True),
        (is_sber_club('ЦП и ЗП "Айсберг"', "Cp_i_zp_aysberg"), False), (is_sber_club("JusTTri"), False),
        (infer_place_by([{"status": "FIN", "place_abs": 1, "chip_time_s": 10, "gun_time_s": 12},
                         {"status": "FIN", "place_abs": 2, "chip_time_s": 9, "gun_time_s": 13}]), "gun"),
    ]
    bad = [f"#{i}: получили {got!r}, ждали {exp!r}" for i, (got, exp) in enumerate(cases) if got != exp]
    return (not bad), ("ok" if not bad else "; ".join(bad))
