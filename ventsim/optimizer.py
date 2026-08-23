"""
Suggests regulator and fan adjustments so that dust concentration at every
monitored branch stays under a target exposure limit.

Strategy (mirrors how a ventilation engineer would actually respond):
  1. Try opening the district's own regulator further first (cheapest,
     most local fix, doesn't affect other districts as much).
  2. If the regulator is already fully open and the district is still over
     limit, recommend raising the main fan speed instead.
  3. If neither gets there within realistic equipment limits, flag that a
     booster/auxiliary fan or additional dust suppression is required.

This uses simple bisection against the real solver (not a closed-form
shortcut) so it stays correct even after the network topology is edited.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .network import Network
from .solver import solve


@dataclass
class Suggestion:
    branch_id: str
    branch_name: str
    current_concentration: float
    limit: float
    action: str          # human-readable description
    kind: str             # "regulator", "fan", "infeasible", "ok"
    target_value: float | None = None   # suggested opening_pct or fan speed


def _concentration_for(net: Network, branch_id: str) -> float:
    result = solve(net)
    return result.branch_results[branch_id].dust_concentration


def suggest_for_branch(net: Network, branch_id: str, limit: float,
                        regulator_branch_id: str | None = None,
                        fan_branch_id: str | None = None,
                        max_fan_speed: float = 1.4) -> Suggestion:
    branch_name = net.branches[branch_id].name
    current = _concentration_for(net, branch_id)

    if current <= limit:
        return Suggestion(branch_id, branch_name, current, limit,
                           action=f"{branch_name} is within the limit ({current:.2f} mg/m3).",
                           kind="ok")

    # --- Attempt 1: open the district regulator ---
    if regulator_branch_id is not None:
        reg = net.branches[regulator_branch_id].regulator
        if reg is not None and reg.opening_pct < 100.0 - 1e-6:
            trial = deepcopy(net)
            trial.branches[regulator_branch_id].regulator.opening_pct = 100.0
            best_conc = _concentration_for(trial, branch_id)
            if best_conc <= limit:
                lo, hi = reg.opening_pct, 100.0
                for _ in range(30):
                    mid = (lo + hi) / 2
                    trial = deepcopy(net)
                    trial.branches[regulator_branch_id].regulator.opening_pct = mid
                    c = _concentration_for(trial, branch_id)
                    if c <= limit:
                        hi = mid
                    else:
                        lo = mid
                return Suggestion(
                    branch_id, branch_name, current, limit,
                    action=(f"Open the regulator on {net.branches[regulator_branch_id].name} "
                            f"from {reg.opening_pct:.0f}% to about {hi:.0f}% to bring "
                            f"{branch_name} back under {limit:.1f} mg/m3."),
                    kind="regulator", target_value=round(hi, 1),
                )

    # --- Attempt 2: raise main fan speed ---
    if fan_branch_id is not None:
        fan = net.branches[fan_branch_id].fan
        if fan is not None:
            trial = deepcopy(net)
            trial.branches[fan_branch_id].fan.speed = max_fan_speed
            if regulator_branch_id is not None and trial.branches[regulator_branch_id].regulator is not None:
                trial.branches[regulator_branch_id].regulator.opening_pct = 100.0
            best_conc = _concentration_for(trial, branch_id)
            if best_conc <= limit:
                lo, hi = fan.speed, max_fan_speed
                for _ in range(30):
                    mid = (lo + hi) / 2
                    trial = deepcopy(net)
                    trial.branches[fan_branch_id].fan.speed = mid
                    if regulator_branch_id is not None and trial.branches[regulator_branch_id].regulator is not None:
                        trial.branches[regulator_branch_id].regulator.opening_pct = 100.0
                    c = _concentration_for(trial, branch_id)
                    if c <= limit:
                        hi = mid
                    else:
                        lo = mid
                pct_increase = (hi / fan.speed - 1.0) * 100.0
                return Suggestion(
                    branch_id, branch_name, current, limit,
                    action=(f"Fully open district regulators and raise the main fan speed "
                            f"from {fan.speed*100:.0f}% to about {hi*100:.0f}% "
                            f"({pct_increase:+.0f}%) to bring {branch_name} under {limit:.1f} mg/m3."),
                    kind="fan", target_value=round(hi, 3),
                )

    return Suggestion(
        branch_id, branch_name, current, limit,
        action=(f"{branch_name} cannot be brought under {limit:.1f} mg/m3 with the main fan "
                f"and regulators alone \u2014 consider an auxiliary/booster fan in that district "
                f"or additional dust suppression (water sprays, scrubber) at the source."),
        kind="infeasible",
    )
