# Mine Ventilation & Dust Simulator

A simulator of an underground mine ventilation network. It shows how airflow
quantity redistributes through the network as mine conditions change (dust
generation at the working faces), and how **regulators** and the **main fan**
can be adjusted to restore safe airflow distribution.

Two parts, sharing the same physics:

- **`ventsim/`** — a reusable Python engine: network model, a general
  Hardy-Cross solver (Kirchhoff's laws for airflow, à la McPherson's
  *Subsurface Ventilation and Environmental Engineering*), a dust-transport
  model, and an optimizer that suggests regulator/fan changes to meet a dust
  limit. Fully unit tested.
- **`web/index.html`** — a self-contained, interactive browser UI (no server
  needed) with a live network schematic, sliders for the fan and regulators,
  and the same suggestion logic, so you can explore the network in real time.

## Quick start

### Web UI (no install required)
Just open `web/index.html` in a browser.

### Python engine
```bash
python3 -m venv .venv && source .venv/bin/activate      # optional but recommended
pip install -r requirements.txt

python3 -m ventsim.cli report                            # solve & print all branches
python3 -m ventsim.cli suggest --regulator-setting 30 --limit 2.0
python3 -m ventsim.cli sweep --regulator b3 --branch b5 --limit 2.0
pytest tests/ -v
```

## The network

A fixed example layout (see `ventsim/example_network.py`), representative of
a small two-district room-and-pillar mine:

```
surface ---[Downcast Shaft]--- shaft bottom ---[Main Intake]--- split
                                                                   |
                                    +------------------------------+
                                    |                              |
                          [Regulator + Intake A]         [Regulator + Intake B]
                                    |                              |
                             District A face               District B face
                            (dust source A)                (dust source B)
                                    |                              |
                          [District A Return]           [District B Return]
                                    |                              |
                                    +------------------------------+
                                                   |
                                      return junction ---[Main Return]---
                                      upcast shaft ---[Main Fan]--- surface
```

The layout is fixed for now — the solver itself is fully general (it finds
independent loops automatically via a spanning-tree/chord decomposition), so
adding branches, districts, or extra fans in `example_network.py` (or a
future network editor) works without touching the solver.

## The physics

**Airflow.** Every airway obeys the Atkinson square law, the mine-ventilation
analogue of Ohm's law:

```
H = R * Q * |Q|
```

where `H` is frictional pressure drop (Pa), `R` is the airway's resistance
(`Ns²/m⁸`), and `Q` is airflow quantity (`m³/s`). Kirchhoff's node law (flow
in = flow out at every junction) and loop law (pressure drops around any
closed loop sum to zero, net of fan pressure) apply exactly as they do in a
resistive electrical circuit. The solver (`ventsim/solver.py`) applies the
classical **Hardy-Cross method**: start from a flow guess that already
satisfies continuity, then repeatedly correct each independent loop until
the mesh balances.

**Regulators.** A regulator throttles an airway like an adjustable orifice;
resistance rises with the square of how far it's closed:

```
R_regulator(opening%) = R_ref * (100 / opening%)²
```

Opening a regulator lets more air into that district (at the expense of
districts sharing the same fan and trunk airways); closing it forces air
elsewhere.

**Fans.** The main fan has a drooping quadratic characteristic curve, scaled
by the affinity laws for speed changes:

```
H_fan(Q) = speed² * H0 - k * Q²
```

**Dust.** Each working face generates dust at a fixed rate (mg/s). The
concentration of air leaving a branch is the upstream concentration plus
that generation rate divided by the airflow quantity passing through it
(more air = more dilution). At every junction where airways merge,
downstream concentration is the flow-weighted average of the merging
streams — exactly like mixing two streams of different strength.

**Fresh air boundary.** The model closes the full mine circuit with a
zero-resistance "atmosphere" branch (so the fan's pressure balances against
the whole network, per Kirchhoff's loop law) but dust concentration is not
carried across it — the intake is always fresh outdoor air, since
contaminated return air does not actually recirculate into the intake.

## The optimizer

Given a branch (usually a working face) and a dust exposure limit,
`ventsim/optimizer.py` (and the mirrored logic in the web UI) tries, in
order:

1. **Open that district's regulator** further — cheapest and most local fix.
2. **Raise the main fan speed** (with regulators fully open) if the
   regulator alone can't get there.
3. **Flag it as infeasible** with the equipment modeled — recommending an
   auxiliary/booster fan or additional dust suppression at the source —
   if neither reaches the limit within realistic equipment ranges.

It finds the *minimum* change needed by bisection search against the real
solver, so it stays correct even if the network is edited later.

## Project layout

```
ventsim/
  network.py           data model: Node, Branch, Regulator, Fan, DustSource
  solver.py             general Hardy-Cross airflow + dust solver
  example_network.py    the fixed two-district example layout
  optimizer.py           regulator/fan suggestion engine
  serialize.py           dict/JSON views of the network & results
  cli.py                 command-line report / sweep / suggest
tests/
  test_solver.py         unit tests (continuity, convergence, regulators,
                          fan response, dust mixing, optimizer)
web/
  index.html             interactive browser UI (physics mirrored in JS,
                          verified to match the Python solver to 5+ sig figs)
requirements.txt
```

## Extending it

- **Editable network**: `Network`, `Branch`, `Node` are plain dataclasses —
  a UI that adds/removes branches and calls `solve()` again works today; the
  solver doesn't assume any fixed topology.
- **More districts / loops / booster fans**: just add branches and nodes in
  `example_network.py` (or build a `Network` programmatically); the solver's
  loop-finding is fully general.
- **Serve the Python engine to the web UI**: `ventsim/serialize.py` gives
  JSON-ready dicts for exactly this purpose — wrap `solve()` in a small
  Flask/FastAPI endpoint if you want the browser calling into the real
  Python engine instead of (or in addition to) the JS mirror.
