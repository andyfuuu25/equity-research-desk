"""S&P 500 factor-universe snapshot: loading and percentile ranking.

The snapshot file (``universe_snapshot.json``, produced by
``build_universe.py``) holds the five raw factor values for every S&P 500
constituent. When present and fresh, the evaluator scores each factor as a
sector-relative percentile rank against this universe instead of against
fixed reference thresholds.
"""

import json
import os
from datetime import date

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "universe_snapshot.json")
MAX_AGE_DAYS = 30
MIN_SECTOR_COHORT = 20

# Direction of "good" per factor: True when a higher raw value is better.
HIGHER_IS_BETTER = {
    "ey": True,
    "mom": True,
    "gp": True,
    "accruals": False,  # Sloan (1996): lower accruals = cleaner earnings
    "idio_vol": False,  # low-volatility anomaly
}

_cache = {"mtime": None, "snapshot": None}


def load_snapshot(path=SNAPSHOT_PATH):
    """Return (snapshot dict, age_days) or (None, None) if absent/stale/invalid."""
    try:
        mtime = os.path.getmtime(path)
        if _cache["mtime"] != mtime:
            with open(path, encoding="utf-8") as f:
                _cache["snapshot"] = json.load(f)
            _cache["mtime"] = mtime
        snapshot = _cache["snapshot"]
        age_days = (date.today() - date.fromisoformat(snapshot["as_of"])).days
    except (OSError, ValueError, KeyError):
        return None, None
    if age_days > MAX_AGE_DAYS or not snapshot.get("factors"):
        return None, None
    return snapshot, age_days


def percentile_rank(value, cohort, higher_is_better):
    """Midrank percentile of ``value`` within ``cohort`` (0-100).

    100 is always "good": ranks are flipped for lower-is-better factors.
    """
    vals = [v for v in cohort if v is not None]
    if value is None or not vals:
        return None
    below = sum(1 for v in vals if v < value)
    ties = sum(1 for v in vals if v == value)
    pct = (below + 0.5 * ties) / len(vals) * 100
    if not higher_is_better:
        pct = 100 - pct
    return pct


def rank_factors(raw_factors, sector, snapshot):
    """Percentile-rank ``raw_factors`` ({key: value|None}) against the snapshot.

    Uses the same-sector cohort when it has at least MIN_SECTOR_COHORT names,
    otherwise the full universe. Returns (scores, benchmark_label) where
    scores maps factor key -> percentile (None when unscorable).
    """
    universe = snapshot["factors"].values()
    sector_cohort = [f for f in universe if f.get("sector") == sector]
    if len(sector_cohort) >= MIN_SECTOR_COHORT:
        cohort, cohort_name = sector_cohort, f"{sector} sector"
    else:
        cohort, cohort_name = list(universe), "full index"

    scores = {
        key: percentile_rank(
            raw_factors.get(key),
            [f.get(key) for f in cohort],
            HIGHER_IS_BETTER[key],
        )
        for key in HIGHER_IS_BETTER
    }
    benchmark = (
        f"{cohort_name}, {len(cohort)} S&P 500 names, snapshot {snapshot['as_of']}"
    )
    return scores, benchmark
