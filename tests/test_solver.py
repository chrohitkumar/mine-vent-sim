import math
from collections import defaultdict

import pytest

from ventsim import build_example_network, solve, suggest_for_branch


def test_continuity_holds_at_every_node():
    net = build_example_network()
    res = solve(net)
    balance = defaultdict(float)
    for b in net.branch_list():
        q = res.branch_results[b.id].q
        balance[b.from_node] -= q
        balance[b.to_node] += q
    for node, bal in balance.items():
        assert math.isclose(bal, 0.0, abs_tol=1e-4), f"continuity violated at {node}: {bal}"


def test_solver_converges():
    net = build_example_network()
    res = solve(net)
    assert res.converged


def test_flow_splits_toward_lower_resistance_district():
    """District A has lower total resistance than District B, so it should
    receive more airflow."""
    net = build_example_network()
    res = solve(net)
    assert res.branch_results["b3"].q > res.branch_results["b4"].q


def test_closing_a_regulator_reduces_its_district_flow():
    net = build_example_network()
    base = solve(net)
    q_before = base.branch_results["b3"].q

    net.branches["b3"].regulator.opening_pct = 25.0
    throttled = solve(net)
    q_after = throttled.branch_results["b3"].q

    assert q_after < q_before


def test_closing_a_regulator_raises_local_dust_and_diverts_air_to_other_district():
    net = build_example_network()
    base = solve(net)
    q_b_before = base.branch_results["b4"].q

    net.branches["b3"].regulator.opening_pct = 20.0
    throttled = solve(net)

    assert throttled.branch_results["b5"].dust_concentration > base.branch_results["b5"].dust_concentration
    assert throttled.branch_results["b4"].q > q_b_before  # more air diverted to District B


def test_raising_fan_speed_increases_total_flow_and_lowers_dust():
    net = build_example_network()
    base = solve(net)
    base_dust_a = base.branch_results["b5"].q

    net.branches["b10"].fan.speed = 1.25
    boosted = solve(net)

    assert boosted.branch_results["b10"].q > base.branch_results["b10"].q
    assert boosted.branch_results["b5"].dust_concentration < base.branch_results["b5"].dust_concentration


def test_dust_mixes_by_flow_weighted_average_at_return_junction():
    net = build_example_network()
    res = solve(net)
    qa = res.branch_results["b7"].q
    qb = res.branch_results["b8"].q
    ca = res.branch_results["b7"].dust_concentration
    cb = res.branch_results["b8"].dust_concentration
    expected = (ca * qa + cb * qb) / (qa + qb)
    assert math.isclose(res.branch_results["b9"].dust_concentration, expected, rel_tol=1e-6)


def test_atmosphere_branch_does_not_recirculate_dust():
    """Concentration at the fresh-air intake side must stay at 0 regardless
    of how contaminated the return air is."""
    net = build_example_network()
    net.branches["b5"].dust_source.generation_rate = 5000.0  # heavily contaminate District A
    res = solve(net)
    assert res.branch_results["b1"].dust_concentration == 0.0
    assert res.branch_results["b2"].dust_concentration == 0.0


def test_optimizer_suggests_regulator_fix_when_achievable():
    net = build_example_network()
    net.branches["b3"].regulator.opening_pct = 30.0
    suggestion = suggest_for_branch(net, "b5", limit=3.2,
                                     regulator_branch_id="b3", fan_branch_id="b10")
    assert suggestion.kind == "regulator"
    assert suggestion.target_value is not None

    net.branches["b3"].regulator.opening_pct = suggestion.target_value
    check = solve(net)
    assert check.branch_results["b5"].dust_concentration <= 3.2 + 1e-2


def test_optimizer_suggests_fan_when_regulator_alone_is_not_enough():
    net = build_example_network()
    net.branches["b3"].regulator.opening_pct = 30.0
    suggestion = suggest_for_branch(net, "b5", limit=2.6,
                                     regulator_branch_id="b3", fan_branch_id="b10")
    assert suggestion.kind == "fan"


def test_optimizer_flags_infeasible_limits():
    net = build_example_network()
    net.branches["b3"].regulator.opening_pct = 30.0
    suggestion = suggest_for_branch(net, "b5", limit=0.5,
                                     regulator_branch_id="b3", fan_branch_id="b10",
                                     max_fan_speed=1.4)
    assert suggestion.kind == "infeasible"


def test_optimizer_reports_ok_when_already_within_limit():
    net = build_example_network()
    suggestion = suggest_for_branch(net, "b5", limit=100.0,
                                     regulator_branch_id="b3", fan_branch_id="b10")
    assert suggestion.kind == "ok"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
