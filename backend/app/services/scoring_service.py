from typing import Optional, Dict, Any, List


class ScoringService:
    @staticmethod
    def calculate_points(
        is_correct: bool,
        response_time_ms: int,
        scoring_config: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Calculates server-authoritative points awarded for an answer attempt.
        Never relies on client-supplied points or elapsed time.
        """
        config = scoring_config or {}
        wrong_points = config.get("wrong_answer_points", 0)
        
        if not is_correct:
            return wrong_points

        speed_enabled = config.get("speed_scoring_enabled", True)
        base_points = config.get("base_points", 100)

        if not speed_enabled:
            return base_points

        # Tiers calculation
        tiers: List[Dict[str, Any]] = config.get("tiers", [])
        if not tiers:
            # Standard default tiers
            tiers = [
                {"min_time_s": 0.0, "max_time_s": 2.0, "points": 100},
                {"min_time_s": 2.0, "max_time_s": 5.0, "points": 90},
                {"min_time_s": 5.0, "max_time_s": 10.0, "points": 75},
                {"min_time_s": 10.0, "max_time_s": 15.0, "points": 50},
                {"min_time_s": 15.0, "max_time_s": 20.0, "points": 25},
                {"min_time_s": 20.0, "max_time_s": 99999.0, "points": 10},
            ]

        response_time_s = max(0.0, response_time_ms / 1000.0)

        for tier in tiers:
            min_s = float(tier.get("min_time_s", 0.0))
            max_s = float(tier.get("max_time_s", 99999.0))
            pts = int(tier.get("points", 10))
            if min_s <= response_time_s < max_s:
                return pts

        # Fallback to the lowest points tier if time exceeds all configured ranges
        if tiers:
            return int(tiers[-1].get("points", 10))
        return base_points


scoring_service = ScoringService()
