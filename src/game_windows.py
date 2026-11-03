"""Shared NBA clock-window predicates for venue comparisons.

Periods 1-4 are regulation. A final-N-minute regulation sample is defined only by
the fourth-quarter ESPN clock, and excludes overtime by construction.
"""
from __future__ import annotations


def is_final_regulation_window(period, clock_s_remaining, minutes: float = 10) -> bool:
    """Return true in the final ``minutes`` of the fourth quarter, never overtime."""
    try:
        p, remaining = int(period), float(clock_s_remaining)
    except (TypeError, ValueError):
        return False
    if p != 4 or not 0 <= remaining <= 12 * 60:
        return False
    return remaining <= minutes * 60


def final_regulation_mask(periods, clocks_s_remaining, minutes: float = 10):
    """Vectorized adapter that delegates each row to the canonical predicate."""
    return [is_final_regulation_window(p, c, minutes) for p, c in
            zip(periods, clocks_s_remaining)]


def is_overtime(period) -> bool:
    """True for NBA overtime periods, separate from regulation windows."""
    try:
        return int(period) > 4
    except (TypeError, ValueError):
        return False
