from app.modules.rating.calculator import (
    _calculate_score,
    calculate_running_score,
    calculate_ski_score,
    calculate_trail_score,
    calculate_triathlon_score,
)


def test_run_calculator():
    # 10000m, norm 1760s, time 2400s -> 1760 / 2400 * 1000 = 733.333...
    pts, reason, breakdown = _calculate_score(
        status="FIN",
        duplicate_of=None,
        gender="M",
        distance_class="10000m",
        event_date="2026-05-01",
        chip_time_s=2400.0,
        norm_value=1760.0,
        norm_unit="s",
        norm_year=2026,
        sport="run",
    )
    assert pts is not None
    assert round(pts, 2) == 733.33
    assert reason is None
    assert breakdown["formula"] == "1760 / 2400 × 1000"


def test_ski_and_biathlon_calculator():
    # 100 finishers, place 1 -> 100.0
    pts, reason, breakdown = _calculate_score(
        status="FIN",
        duplicate_of=None,
        gender="M",
        event_date="2026-02-01",
        sport="ski",
        finishers_count=100,
        place=1,
    )
    assert pts == 100.0
    assert reason is None
    assert breakdown["formula"] == "100 × (100 - 1 + 1) / 100"

    # Biathlon: 80 finishers, place 10 -> 88.75
    pts_b, reason_b, breakdown_b = _calculate_score(
        status="FIN",
        duplicate_of=None,
        gender="F",
        event_date="2026-02-15",
        sport="biathlon",
        finishers_count=80,
        place=10,
    )
    assert pts_b == 88.75
    assert reason_b is None

    # RL marathon with 1524 RL points -> 1524 / 7 = 217.714...
    pts_rl, reason_rl, breakdown_rl = _calculate_score(
        status="FIN",
        duplicate_of=None,
        gender="M",
        event_date="2026-03-01",
        sport="ski",
        is_rl_series=True,
        rl_points=1524.0,
    )
    assert round(pts_rl, 2) == 217.71
    assert breakdown_rl["formula"] == "1524 / 7"


def test_triathlon_calculator():
    # Olympic (Rmax=2500), winner Ta=7200s, Tl=7200s, Tmed=8400s -> Bmed=40.0, K=1.0 -> 2540.0
    pts, reason, breakdown = _calculate_score(
        status="FIN",
        duplicate_of=None,
        gender="M",
        distance_class="olympic",
        event_date="2026-06-01",
        chip_time_s=7200.0,
        sport="triathlon",
        leader_time_s=7200.0,
        median_time_s=8400.0,
        special="regular",
    )
    assert pts == 2540.0
    assert reason is None
    assert breakdown["b_med"] == 40.0

    # Half (Rmax=5000), worlds status (K=1.10), Ta=18000s, Tl=15000s, Tmed=17000s (Bmed=0) -> 4400.0
    pts_half, _, breakdown_half = _calculate_score(
        status="FIN",
        duplicate_of=None,
        gender="M",
        distance_class="half",
        event_date="2026-07-01",
        chip_time_s=18000.0,
        sport="triathlon",
        leader_time_s=15000.0,
        median_time_s=17000.0,
        special="worlds",
    )
    assert pts_half == 4400.0
    assert breakdown_half["b_med"] == 0.0


def test_trail_calculator():
    # 50km, D+=2500m -> Rmax=750, Tl=18000s, Ta=21600s, Tmed=23400s -> Bmed=60.0 -> points=660.0
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
    assert pts == 660.0
    assert reason is None
    assert breakdown["r_max"] == 750.0
    assert breakdown["b_med"] == 60.0

    # Without D+ -> missing_elevation_gain
    pts_no_d, reason_no_d, _ = _calculate_score(
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
    assert pts_no_d is None
    assert reason_no_d == "missing_elevation_gain"


def test_pure_calculators_direct_call():
    # Test pure functions directly
    run_res = calculate_running_score(
        status="FIN",
        duplicate_of=None,
        gender="F",
        distance_class="5000m",
        event_date="2026-05-01",
        chip_time_s=1200.0,
        norm_value=965.0,
        norm_unit="s",
        norm_year=2026,
    )
    assert run_res.reason is None
    assert round(run_res.points, 2) == round(965.0 / 1200.0 * 1000.0, 2)
    assert run_res.breakdown["formula_version"] == "run-v1"

    ski_res = calculate_ski_score(
        status="FIN",
        duplicate_of=None,
        gender="M",
        event_date="2026-01-10",
        finishers_count=50,
        place=5,
    )
    assert ski_res.reason is None
    assert ski_res.points == 100.0 * (50 - 5 + 1) / 50
    assert ski_res.breakdown["formula_version"] == "ski-v1"

    tri_res = calculate_triathlon_score(
        status="FIN",
        duplicate_of=None,
        gender="M",
        distance_class="sprint",
        event_date="2026-07-04",
        chip_time_s=3600.0,
        leader_time_s=3600.0,
        median_time_s=4200.0,
        special="regular",
    )
    assert tri_res.reason is None
    assert tri_res.breakdown["formula_version"] == "triathlon-v1"

    trail_res = calculate_trail_score(
        status="FIN",
        duplicate_of=None,
        gender="F",
        distance_km=30.0,
        elevation_gain_m=1200.0,
        event_date="2026-09-01",
        chip_time_s=14400.0,
        leader_time_s=12000.0,
        median_time_s=15000.0,
    )
    assert trail_res.reason is None
    assert trail_res.points > 0
    assert trail_res.breakdown["formula_version"] == "trail-v1"

