"""
Core data model for an underground mine ventilation network.

Physics convention (standard mine ventilation / Atkinson square-law):
    H = R * Q * |Q|
where
    H  : frictional pressure drop across an airway   [Pa]
    R  : Atkinson resistance of the airway           [Ns^2/m^8]
    Q  : airflow quantity through the airway         [m^3/s]

A branch may also contain:
    - a regulator: an adjustable orifice added in series that increases
      the branch's effective resistance as it is throttled closed.
    - a fan: a pressure-adding device whose head depends on the flow
      through it and on the fan's running speed (affinity laws).
    - a dust source: a contaminant generation rate (mg/s) that raises the
      dust concentration of the air leaving the branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


AIR_DENSITY = 1.2  # kg/m^3, standard reference used for velocity/quantity checks


@dataclass
class Regulator:
    """An adjustable door/orifice placed in an airway to control split of flow.

    `opening_pct` is the percentage the regulator is open (5-100).
    Resistance rises with the square of how far it is throttled, which
    mirrors the orifice equation H = R * Q^2 with R ~ 1/area^2.
    """
    ref_resistance: float = 0.02   # resistance contributed at opening_pct = 100
    opening_pct: float = 100.0
    min_opening_pct: float = 5.0   # regulators are never fully sealed in this model

    def resistance(self) -> float:
        opening = max(self.opening_pct, self.min_opening_pct)
        return self.ref_resistance * (100.0 / opening) ** 2


@dataclass
class Fan:
    """A quadratic fan characteristic curve with an adjustable speed setting.

    H_fan(Q) = speed^2 * H0 - k * Q^2

    `speed` is a fraction of rated speed (1.0 = rated, >1.0 = boosted,
    values above ~1.3 are not achievable by a real fan and are flagged
    by the optimizer as "install a booster fan" instead).
    """
    shutoff_pressure: float = 2800.0   # H0, Pa, pressure at zero flow at rated speed
    curve_k: float = 3.4               # Pa / (m^3/s)^2, how fast head falls off with flow
    speed: float = 1.0

    def pressure(self, q: float) -> float:
        return (self.speed ** 2) * self.shutoff_pressure - self.curve_k * q * q


@dataclass
class DustSource:
    """A contaminant generation point (e.g. a continuous miner cutting coal/rock)."""
    generation_rate: float = 40.0   # mg/s
    label: str = "face"


@dataclass
class Branch:
    id: str
    from_node: str
    to_node: str
    name: str
    length_m: float
    base_resistance: float                     # airway wall-friction resistance
    regulator: Optional[Regulator] = None
    fan: Optional[Fan] = None
    dust_source: Optional[DustSource] = None
    area_m2: float = 12.0                       # cross-sectional area, for velocity display
    is_atmosphere: bool = False                 # True for the virtual pressure-closing branch
    # (models surface_out/surface_in as the same barometric datum for the
    # airflow solve; it does NOT represent contaminated return air actually
    # recirculating into the intake, so dust concentration is not carried
    # across it - the intake side is always treated as fresh outdoor air).

    def total_passive_resistance(self) -> float:
        r = self.base_resistance
        if self.regulator is not None:
            r += self.regulator.resistance()
        return r


@dataclass
class Node:
    id: str
    name: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class Network:
    nodes: dict[str, Node] = field(default_factory=dict)
    branches: dict[str, Branch] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_branch(self, branch: Branch) -> None:
        self.branches[branch.id] = branch

    def branch_list(self) -> list[Branch]:
        return list(self.branches.values())
