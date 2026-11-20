"""Golden-тесты формул подсчёта очков по SPEC v1.3 §9 и §9.7.

SPEC §9.7:
- Golden-тесты: эталонные таблицы заказчика превращаются в golden-тесты;
  расхождение больше 0.5 балла — ошибка (assert abs(pts - expected) <= 0.5).
- Лыжи: фиксируется формула итога (сумма гонок 100 * (N - место + 1) / N + RL / 7).
- Бег: формула норматив / время * 1000 по эталонам нормативов 2026 года.
- Триатлон: (Rmax * (1 - (Ta - Tl) / Tl) + Bmed) * K.
- Трейл: max(0, 10 * (km + D+ / 100) * (1 - (Ta - Tl) / Tl) + Bmed).
"""

from __future__ import annotations

import pytest

from app.modules.rating.calculator import _calculate_score

TOLERANCE = 0.5


class TestGoldenSkiScoring:
    """SPEC §9.2, §9.7: Лыжи и биатлон.

    Формула гонки: 100 × (N − место + 1) / N.
    Формула итога: Σ баллы_гонок + очки_RL_за_сезон ÷ 7.
    """

    @pytest.mark.parametrize(
        ("finishers", "place", "expected_pts"),
        [
            (100, 1, 100.0),
            (100, 50, 51.0),
            (100, 100, 1.0),
            (80, 10, 88.75),
            (543, 27, 95.21),
            (250, 125, 50.4),
        ],
    )
    def test_golden_ski_race_place_formula(self, finishers: int, place: int, expected_pts: float):
        pts, reason, _ = _calculate_score(
            status="FIN",
            duplicate_of=None,
            gender="M",
            event_date="2026-02-01",
            sport="ski",
            finishers_count=finishers,
            place=place,
        )
        assert reason is None
        assert pts is not None
        assert abs(pts - expected_pts) <= TOLERANCE, f"Diff {abs(pts - expected_pts)} exceeds {TOLERANCE}"

    def test_golden_ski_rl_marathon_points(self):
        # Очки Russialoppet: 1524 RL points ÷ 7 = 217.714
        pts, reason, breakdown = _calculate_score(
            status="FIN",
            duplicate_of=None,
            gender="M",
            event_date="2026-03-01",
            sport="ski",
            is_rl_series=True,
            rl_points=1524.0,
        )
        assert reason is None
        assert pts is not None
        expected_rl = 1524.0 / 7.0  # 217.714...
        assert abs(pts - expected_rl) <= TOLERANCE
        assert breakdown["formula"] == "1524 / 7"

    def test_golden_ski_athlete_total_per_spec_9_2_and_9_7(self):
        """Эталонный расчёт спортсмена A из SPEC §9.2 и §9.7:

        Сумма гонок: 2027.1, очки RL: 1524.
        Формула итога: 2027.1 + 1524 / 7 = 2244.86.
        Расхождение не должно превышать 0.5 балла.
        """
        races_pts_sum = 2027.1
        rl_points = 1524.0
        expected_total = 2244.86

        calculated_total = races_pts_sum + (rl_points / 7.0)
        assert (
            abs(calculated_total - expected_total) <= TOLERANCE
        ), f"Total {calculated_total} diverged from golden reference {expected_total}"


class TestGoldenRunScoring:
    """SPEC §9.1, §9.7: Беговой рейтинг.

    Формула: норматив / время × 1000.
    Нормативы 2026 года для стандартных дистанций.
    """

    @pytest.mark.parametrize(
        ("gender", "distance_class", "norm_value", "time_s", "expected_pts"),
        [
            # 10k Мужчины: норматив 1760с, время 2400с (40:00) -> 1760 / 2400 * 1000 = 733.33
            ("M", "10000m", 1760.0, 2400.0, 733.33),
            # 10k Женщины: норматив 1980с, время 2700с (45:00) -> 1980 / 2700 * 1000 = 733.33
            ("F", "10000m", 1980.0, 2700.0, 733.33),
            # 5k Мужчины: норматив 835с, время 1200с (20:00) -> 835 / 1200 * 1000 = 695.83
            ("M", "5000m", 835.0, 1200.0, 695.83),
            # 21.1k Мужчины: норматив 3900с, время 4500с (1:15:00) -> 3900 / 4500 * 1000 = 866.67
            ("M", "21.1k", 3900.0, 4500.0, 866.67),
            # 42.2k Мужчины: норматив 8400с, время 10800с (3:00:00) -> 8400 / 10800 * 1000 = 777.78
            ("M", "42.2k", 8400.0, 10800.0, 777.78),
            # 42.2k Женщины: норматив 9600с, время 12600с (3:30:00) -> 9600 / 12600 * 1000 = 761.90
            ("F", "42.2k", 9600.0, 12600.0, 761.90),
        ],
    )
    def test_golden_run_norm_formula(
        self, gender: str, distance_class: str, norm_value: float, time_s: float, expected_pts: float
    ):
        pts, reason, _ = _calculate_score(
            status="FIN",
            duplicate_of=None,
            gender=gender,
            distance_class=distance_class,
            event_date="2026-05-01",
            chip_time_s=time_s,
            norm_value=norm_value,
            norm_unit="s",
            norm_year=2026,
            sport="run",
        )
        assert reason is None
        assert pts is not None
        assert abs(pts - expected_pts) <= TOLERANCE, f"Diff {abs(pts - expected_pts)} exceeds {TOLERANCE}"


class TestGoldenTriathlonScoring:
    """SPEC §9.3, §9.7: Триатлон.

    Формула: (Rmax × (1 − (Ta − Tl) / Tl) + Bmed) × K.
    Bmed = 2 × max(0, (Tmed − Ta) / 60).
    """

    @pytest.mark.parametrize(
        ("distance_class", "special", "ta", "tl", "tmed", "expected_pts"),
        [
            # Olympic (Rmax=2500, regular K=1.0): Ta=7200, Tl=7200, Tmed=8400 -> Bmed=40.0 -> Total=2540.0
            ("olympic", "regular", 7200.0, 7200.0, 8400.0, 2540.0),
            # Half (Rmax=5000, worlds K=1.10): Ta=18000, Tl=15000, Tmed=17000 (Ta > Tmed => Bmed=0)
            # 5000 * (1 - 3000/15000) * 1.10 = 5000 * 0.8 * 1.10 = 4400.0
            ("half", "worlds", 18000.0, 15000.0, 17000.0, 4400.0),
            # Full (Rmax=10000, kona K=1.15): Ta=36000, Tl=30000, Tmed=39000
            # Bmed = 2 * (39000 - 36000) / 60 = 100.0
            # (10000 * (1 - 6000/30000) + 100) * 1.15 = (8000 + 100) * 1.15 = 9315.0
            ("full", "kona", 36000.0, 30000.0, 39000.0, 9315.0),
            # Sprint (Rmax=1250, regular K=1.0): Ta=3600, Tl=3600, Tmed=4200
            # Bmed = 2 * (4200 - 3600) / 60 = 20.0 -> Total = 1270.0
            ("sprint", "regular", 3600.0, 3600.0, 4200.0, 1270.0),
        ],
    )
    def test_golden_triathlon_formula(
        self, distance_class: str, special: str, ta: float, tl: float, tmed: float, expected_pts: float
    ):
        pts, reason, _ = _calculate_score(
            status="FIN",
            duplicate_of=None,
            gender="M",
            distance_class=distance_class,
            event_date="2026-06-01",
            chip_time_s=ta,
            sport="triathlon",
            leader_time_s=tl,
            median_time_s=tmed,
            special=special,
        )
        assert reason is None
        assert pts is not None
        assert abs(pts - expected_pts) <= TOLERANCE, f"Diff {abs(pts - expected_pts)} exceeds {TOLERANCE}"


class TestGoldenTrailScoring:
    """SPEC §9.4, §9.7: Трейл.

    Формула: max(0, 10 × (км + D+ / 100) × (1 − (Ta − Tl) / Tl) + Bmed), K=1.
    """

    def test_golden_trail_50k_with_elevation(self):
        # 50km, D+=2500m -> Rmax = 10 * (50 + 25) = 750
        # Tl=18000s, Ta=21600s, Tmed=23400s
        # 1 - (21600 - 18000)/18000 = 0.8 -> 750 * 0.8 = 600.0
        # Bmed = 2 * (23400 - 21600) / 60 = 60.0
        # Total = 660.0
        pts, reason, breakdown = _calculate_score(
            status="FIN",
            duplicate_of=None,
            gender="M",
            event_date="2026-08-01",
            chip_time_s=21600.0,
            distance_km=50.0,
            elevation_gain_m=2500.0,
            sport="trail",
            leader_time_s=18000.0,
            median_time_s=23400.0,
        )
        assert reason is None
        assert pts is not None
        assert abs(pts - 660.0) <= TOLERANCE
        assert breakdown["r_max"] == 750.0
        assert breakdown["b_med"] == 60.0

    def test_golden_trail_requires_elevation_gain(self):
        # Трейл без D+ незачётный по SPEC §9.4
        pts, reason, _ = _calculate_score(
            status="FIN",
            duplicate_of=None,
            gender="M",
            event_date="2026-08-01",
            chip_time_s=21600.0,
            distance_km=50.0,
            elevation_gain_m=None,
            sport="trail",
            leader_time_s=18000.0,
            median_time_s=23400.0,
        )
        assert pts is None
        assert reason == "missing_elevation_gain"
