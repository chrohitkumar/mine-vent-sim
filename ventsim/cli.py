"""
Command-line interface for the mine ventilation simulator.

Usage:
    python -m ventsim.cli report
        Solve the default network and print a full branch-by-branch table.

    python -m ventsim.cli sweep --branch b3 --regulator b3 --limit 2.0
        Sweep District A's regulator opening from 10-100% and plot how
        airflow quantity and dust concentration respond, saving a PNG.

    python -m ventsim.cli suggest --branch b5 --limit 2.0
        Print the recommended regulator/fan change to meet a dust limit at
        a given branch (defaults to District A's face, b5).
"""

from __future__ import annotations

import argparse
from copy import deepcopy

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .example_network import build_example_network
from .solver import solve
from .optimizer import suggest_for_branch


def cmd_report(args: argparse.Namespace) -> None:
    net = build_example_network()
    res = solve(net)
    print(f"{'Branch':6} {'Name':38} {'Q (m3/s)':>10} {'v (m/s)':>9} "
          f"{'dP (Pa)':>9} {'Dust (mg/m3)':>13}")
    print("-" * 90)
    for b in net.branch_list():
        r = res.branch_results[b.id]
        print(f"{b.id:6} {b.name:38} {r.q:10.2f} {r.velocity:9.2f} "
              f"{r.pressure_drop:9.1f} {r.dust_concentration:13.2f}")
    print()
    print(f"Solved in {res.iterations} iterations (converged={res.converged})")


def cmd_sweep(args: argparse.Namespace) -> None:
    net = build_example_network()
    openings = list(range(10, 101, 5))
    quantities = []
    dust = []
    for opening in openings:
        trial = deepcopy(net)
        trial.branches[args.regulator].regulator.opening_pct = opening
        res = solve(trial)
        quantities.append(res.branch_results[args.branch].q)
        dust.append(res.branch_results[args.branch].dust_concentration)

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.set_xlabel("Regulator opening (%)")
    ax1.set_ylabel("Airflow quantity Q (m3/s)", color="tab:blue")
    ax1.plot(openings, quantities, color="tab:blue", marker="o")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Dust concentration (mg/m3)", color="tab:red")
    ax2.plot(openings, dust, color="tab:red", marker="s")
    ax2.axhline(args.limit, color="tab:red", linestyle="--", alpha=0.5,
                label=f"limit = {args.limit} mg/m3")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    ax2.legend(loc="upper right")

    plt.title(f"Effect of {args.regulator} opening on {args.branch}")
    fig.tight_layout()
    out_path = args.output
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")


def cmd_suggest(args: argparse.Namespace) -> None:
    net = build_example_network()
    if args.regulator_setting is not None:
        net.branches[args.regulator].regulator.opening_pct = args.regulator_setting
    s = suggest_for_branch(
        net, args.branch, limit=args.limit,
        regulator_branch_id=args.regulator, fan_branch_id=args.fan,
    )
    print(f"Current concentration at {s.branch_name}: {s.current_concentration:.2f} mg/m3 "
          f"(limit {s.limit:.2f} mg/m3)")
    print(f"Recommendation ({s.kind}): {s.action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Underground mine ventilation simulator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="Solve and print the full branch table")
    p_report.set_defaults(func=cmd_report)

    p_sweep = sub.add_parser("sweep", help="Sweep a regulator opening and plot the effect")
    p_sweep.add_argument("--branch", default="b5", help="Branch to observe (default: b5)")
    p_sweep.add_argument("--regulator", default="b3", help="Branch whose regulator to sweep (default: b3)")
    p_sweep.add_argument("--limit", type=float, default=2.0, help="Dust limit line to draw, mg/m3")
    p_sweep.add_argument("--output", default="regulator_sweep.png", help="Output PNG path")
    p_sweep.set_defaults(func=cmd_sweep)

    p_suggest = sub.add_parser("suggest", help="Suggest a fix to bring a branch under a dust limit")
    p_suggest.add_argument("--branch", default="b5", help="Branch to check (default: b5)")
    p_suggest.add_argument("--regulator", default="b3", help="District regulator branch id")
    p_suggest.add_argument("--fan", default="b10", help="Main fan branch id")
    p_suggest.add_argument("--limit", type=float, default=2.0, help="Dust exposure limit, mg/m3")
    p_suggest.add_argument("--regulator-setting", type=float, default=None,
                            help="Optionally set the regulator's current opening %% before checking")
    p_suggest.set_defaults(func=cmd_suggest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
