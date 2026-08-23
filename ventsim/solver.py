"""
Hardy-Cross solver for mine ventilation networks.

The mine ventilation network is mathematically identical to a resistive
electrical network obeying a square (Atkinson) law instead of a linear
(Ohm's) law:

    H_branch = R * Q * |Q|  -  H_fan(Q)

Kirchhoff's laws apply directly:
    - Node law:  the algebraic sum of Q at every junction is zero (air is
      conserved - what flows in must flow out).
    - Loop law:  the algebraic sum of pressure drops (minus any fan boosts)
      around every independent loop is zero.

Because the loop law is non-linear in Q, we solve it with the Hardy-Cross
method: build an initial flow distribution that satisfies the node law
(via a spanning-tree/chord decomposition), then repeatedly apply a
correction to every independent loop until the mesh is balanced. This is
the classical technique used in mine ventilation planning (McPherson,
"Subsurface Ventilation and Environmental Engineering") and generalizes
cleanly to any network topology, which matters if the network is edited
later (branches/loops added or removed). The network must be a single
closed circuit (see `example_network.py`'s atmospheric closing branch).
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .network import Network


@dataclass
class BranchResult:
    id: str
    name: str
    q: float                  # airflow, m^3/s (signed, direction = from_node -> to_node)
    velocity: float            # m/s
    resistance: float          # Atkinson resistance used this solve, Ns^2/m^8
    pressure_drop: float       # Pa, frictional loss (R*Q*|Q|)
    fan_pressure: float        # Pa, pressure added by a fan on this branch (0 if none)
    dust_concentration: float  # mg/m^3 of air leaving this branch (downstream end)


@dataclass
class SolveResult:
    branch_results: dict[str, BranchResult]
    node_concentration: dict[str, float]     # mg/m^3 of air arriving at each node
    iterations: int
    converged: bool


def _build_graph(net: Network) -> nx.MultiGraph:
    g = nx.MultiGraph()
    for node_id in net.nodes:
        g.add_node(node_id)
    for b in net.branch_list():
        g.add_edge(b.from_node, b.to_node, key=b.id, branch_id=b.id)
    return g


def _spanning_tree_and_chords(net: Network) -> tuple[nx.Graph, list[str]]:
    """Pick one branch per node-pair to form a spanning tree; every other
    branch (including any parallel duplicate) is a chord that closes a loop."""
    g = _build_graph(net)
    simple = nx.Graph()
    simple.add_nodes_from(g.nodes())
    pair_to_branch = {}
    for b in net.branch_list():
        pair = frozenset((b.from_node, b.to_node))
        if pair not in pair_to_branch:
            pair_to_branch[pair] = b.id
            simple.add_edge(b.from_node, b.to_node)
    tree = nx.minimum_spanning_tree(simple)
    tree_branch_ids = {pair_to_branch[frozenset((u, v))] for u, v in tree.edges()}
    chord_ids = [b.id for b in net.branch_list() if b.id not in tree_branch_ids]
    return tree, chord_ids


def _fundamental_loops(net: Network) -> list[list[tuple[str, int]]]:
    """Return fundamental loops as lists of (branch_id, orientation), where
    orientation is +1 if traversed from_node->to_node, -1 if reversed."""
    tree, chord_ids = _spanning_tree_and_chords(net)
    loops = []
    for chord_id in chord_ids:
        chord = net.branches[chord_id]
        path = nx.shortest_path(tree, chord.from_node, chord.to_node)
        loop = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            tb = next(b for b in net.branch_list()
                      if {b.from_node, b.to_node} == {u, v} and b.id != chord_id)
            orientation = 1 if (tb.from_node == u and tb.to_node == v) else -1
            loop.append((tb.id, orientation))
        # The tree path already runs chord.from_node -> chord.to_node, so
        # closing the cycle means traversing the chord itself backwards
        # (to_node -> from_node), i.e. orientation -1 relative to its own
        # from_node->to_node definition.
        loop.append((chord_id, -1))
        loops.append(loop)
    return loops


def _initial_flows(net: Network, chord_guess: float = 1.0) -> dict[str, float]:
    """Build a flow assignment (signed, from_node->to_node) that satisfies
    the node continuity law everywhere, using a spanning-tree/chord split:
    chords get an arbitrary guessed flow, then tree-edge flows are
    determined uniquely by back-substitution from leaves to the root."""
    tree, chord_ids = _spanning_tree_and_chords(net)
    q: dict[str, float] = {}

    # net current injected at each node by the chords (+ = net inflow)
    injection: dict[str, float] = {n: 0.0 for n in net.nodes}
    for chord_id in chord_ids:
        b = net.branches[chord_id]
        q[chord_id] = chord_guess
        injection[b.from_node] -= chord_guess
        injection[b.to_node] += chord_guess

    root = next(iter(net.nodes))
    order = list(nx.dfs_postorder_nodes(tree, source=root))
    parent = {root: None}
    for u, v in nx.bfs_tree(tree, source=root).edges():
        parent[v] = u

    subtree_balance = dict(injection)  # accumulates children's balances as we go
    for node in order:
        if node == root:
            continue
        p = parent[node]
        tb = next(b for b in net.branch_list()
                   if {b.from_node, b.to_node} == {node, p})
        # flow leaving `node` towards `p` must carry away everything injected
        # into node's subtree so far (continuity).
        flow_node_to_parent = subtree_balance[node]
        if tb.from_node == node and tb.to_node == p:
            q[tb.id] = flow_node_to_parent
        else:
            q[tb.id] = -flow_node_to_parent
        subtree_balance[p] = subtree_balance.get(p, 0.0) + flow_node_to_parent

    return q


def solve(net: Network, max_iter: int = 300, tolerance: float = 1e-6,
          chord_guess: float = 3.0) -> SolveResult:
    branches = net.branches
    q = _initial_flows(net, chord_guess=chord_guess)
    loops = _fundamental_loops(net)

    converged = False
    it = 0
    for it in range(1, max_iter + 1):
        max_correction = 0.0
        for loop in loops:
            numerator = 0.0
            denominator = 0.0
            for bid, orient in loop:
                b = branches[bid]
                qi = q[bid] * orient  # flow in the loop's traversal direction
                r = b.total_passive_resistance()
                h_friction = r * qi * abs(qi)
                h_fan = b.fan.pressure(abs(qi)) if b.fan else 0.0
                h_fan_signed = h_fan if qi >= 0 else -h_fan
                numerator += h_friction - h_fan_signed
                denominator += 2.0 * r * abs(qi) + (
                    2.0 * b.fan.curve_k * abs(qi) if b.fan else 0.0
                )
            if denominator <= 1e-9:
                continue
            delta = -numerator / denominator
            max_correction = max(max_correction, abs(delta))
            for bid, orient in loop:
                q[bid] += orient * delta
        if max_correction < tolerance:
            converged = True
            break

    # ---- derive dust concentration via topological propagation along flow ----
    # Direction of dependency = direction of airflow. The atmosphere branch is
    # excluded as a *dependency* (its downstream side is defined as fresh air,
    # concentration 0) which is what breaks the physical circuit into a DAG
    # for this purpose - contaminated return air does not recirculate into
    # the intake in this model.
    inbound: dict[str, list[str]] = {n: [] for n in net.nodes}
    for b in net.branch_list():
        qi = q[b.id]
        upstream, downstream = (b.from_node, b.to_node) if qi >= 0 else (b.to_node, b.from_node)
        inbound[downstream].append(b.id)

    node_conc: dict[str, float] = {}
    resolved_branches: dict[str, float] = {}
    node_ready = {n: (len(inbound[n]) == 0) for n in net.nodes}
    for n, ready in node_ready.items():
        if ready:
            node_conc[n] = 0.0

    pending_branches = set(net.branches.keys())
    changed = True
    while changed:
        changed = False
        for bid in list(pending_branches):
            b = net.branches[bid]
            qi = q[bid]
            upstream, downstream = (b.from_node, b.to_node) if qi >= 0 else (b.to_node, b.from_node)
            if b.is_atmosphere:
                c_out = 0.0  # fresh outdoor air enters here, independent of upstream
            elif upstream in node_conc:
                gen = b.dust_source.generation_rate if b.dust_source else 0.0
                qabs = max(abs(qi), 1e-6)
                c_out = node_conc[upstream] + gen / qabs
            else:
                continue  # upstream not resolved yet
            resolved_branches[bid] = c_out
            pending_branches.discard(bid)
            changed = True
            # check if downstream node can now be finalized
            if downstream not in node_conc and all(ib in resolved_branches for ib in inbound[downstream]):
                total_q = 0.0
                weighted = 0.0
                for ib in inbound[downstream]:
                    ib_branch = net.branches[ib]
                    ib_q = abs(q[ib])
                    total_q += ib_q
                    weighted += resolved_branches[ib] * ib_q
                node_conc[downstream] = weighted / total_q if total_q > 1e-9 else 0.0

    branch_results = {}
    for b in net.branch_list():
        qi = q[b.id]
        r = b.total_passive_resistance()
        h_fric = r * qi * abs(qi)
        h_fan = b.fan.pressure(abs(qi)) if b.fan else 0.0
        branch_results[b.id] = BranchResult(
            id=b.id,
            name=b.name,
            q=qi,
            velocity=qi / b.area_m2 if b.area_m2 else 0.0,
            resistance=r,
            pressure_drop=h_fric,
            fan_pressure=h_fan,
            dust_concentration=resolved_branches[b.id],
        )

    return SolveResult(
        branch_results=branch_results,
        node_concentration=node_conc,
        iterations=it,
        converged=converged,
    )
