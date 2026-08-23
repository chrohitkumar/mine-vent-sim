"""
Plain-dict (JSON-ready) views of the network and solve results, so the
engine can be dropped behind a REST API, a notebook, or any other UI
without the caller needing to import the dataclasses directly.
"""

from __future__ import annotations

from .network import Network
from .solver import SolveResult


def network_to_dict(net: Network) -> dict:
    return {
        "nodes": [
            {"id": n.id, "name": n.name, "x": n.x, "y": n.y}
            for n in net.nodes.values()
        ],
        "branches": [
            {
                "id": b.id,
                "from": b.from_node,
                "to": b.to_node,
                "name": b.name,
                "length_m": b.length_m,
                "base_resistance": b.base_resistance,
                "area_m2": b.area_m2,
                "is_atmosphere": b.is_atmosphere,
                "regulator": (
                    {"opening_pct": b.regulator.opening_pct,
                     "ref_resistance": b.regulator.ref_resistance}
                    if b.regulator else None
                ),
                "fan": (
                    {"speed": b.fan.speed, "shutoff_pressure": b.fan.shutoff_pressure,
                     "curve_k": b.fan.curve_k}
                    if b.fan else None
                ),
                "dust_source": (
                    {"generation_rate": b.dust_source.generation_rate, "label": b.dust_source.label}
                    if b.dust_source else None
                ),
            }
            for b in net.branch_list()
        ],
    }


def solve_result_to_dict(result: SolveResult) -> dict:
    return {
        "converged": result.converged,
        "iterations": result.iterations,
        "branches": {
            bid: {
                "q": r.q,
                "velocity": r.velocity,
                "resistance": r.resistance,
                "pressure_drop": r.pressure_drop,
                "fan_pressure": r.fan_pressure,
                "dust_concentration": r.dust_concentration,
            }
            for bid, r in result.branch_results.items()
        },
        "node_concentration": result.node_concentration,
    }
