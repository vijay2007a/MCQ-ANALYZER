from app.services.scoring_service import scoring_service


def test_default_speed_scoring_tiers():
    # 0 - 2 seconds (e.g. 1500 ms) -> 100 points
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=1500) == 100

    # 2 - 5 seconds (e.g. 3500 ms) -> 90 points
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=3500) == 90

    # 5 - 10 seconds (e.g. 7000 ms) -> 75 points
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=7000) == 75

    # 10 - 15 seconds (e.g. 12000 ms) -> 50 points
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=12000) == 50

    # 15 - 20 seconds (e.g. 18000 ms) -> 25 points
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=18000) == 25

    # 20+ seconds (e.g. 25000 ms) -> 10 points
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=25000) == 10


def test_wrong_answer_scoring():
    # Wrong answer always receives wrong_answer_points (0 by default) regardless of speed
    assert scoring_service.calculate_points(is_correct=False, response_time_ms=500) == 0
    assert scoring_service.calculate_points(is_correct=False, response_time_ms=10000) == 0


def test_custom_scoring_configuration():
    custom_config = {
        "base_points": 200,
        "speed_scoring_enabled": True,
        "wrong_answer_points": -10,
        "tiers": [
            {"min_time_s": 0.0, "max_time_s": 3.0, "points": 200},
            {"min_time_s": 3.0, "max_time_s": 999.0, "points": 100},
        ],
    }

    # Fast correct -> 200
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=2000, scoring_config=custom_config) == 200

    # Slower correct -> 100
    assert scoring_service.calculate_points(is_correct=True, response_time_ms=5000, scoring_config=custom_config) == 100

    # Wrong answer -> -10 penalty
    assert scoring_service.calculate_points(is_correct=False, response_time_ms=1000, scoring_config=custom_config) == -10
