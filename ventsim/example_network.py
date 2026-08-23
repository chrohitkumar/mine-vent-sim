"""
A representative (fictional) two-district underground mine ventilation
network, used as the default layout for the simulator.

Layout:

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
                                          upcast shaft ---[Upcast Shaft + Main Fan]--- surface
"""

from __future__ import annotations

from .network import Branch, DustSource, Fan, Network, Node, Regulator


def build_example_network() -> Network:
    net = Network()

    # ---- nodes (with x, y for the SVG schematic layout) ----
    net.add_node(Node("surface_in", "Surface (Intake)", x=60, y=40))
    net.add_node(Node("shaft_bottom", "Shaft Bottom", x=60, y=160))
    net.add_node(Node("split", "Main Split", x=60, y=260))
    net.add_node(Node("faceA_in", "District A Intake", x=220, y=340))
    net.add_node(Node("faceB_in", "District B Intake", x=-100, y=340))
    net.add_node(Node("faceA_out", "District A Face", x=220, y=440))
    net.add_node(Node("faceB_out", "District B Face", x=-100, y=440))
    net.add_node(Node("return_junction", "Return Junction", x=60, y=540))
    net.add_node(Node("upcast_bottom", "Upcast Shaft Bottom", x=60, y=640))
    net.add_node(Node("surface_out", "Surface (Return)", x=60, y=760))

    # ---- branches ----
    net.add_branch(Branch(
        id="b1", from_node="surface_in", to_node="shaft_bottom",
        name="Downcast Shaft", length_m=180, base_resistance=0.015, area_m2=20,
    ))
    net.add_branch(Branch(
        id="b2", from_node="shaft_bottom", to_node="split",
        name="Main Intake Roadway", length_m=250, base_resistance=0.02, area_m2=16,
    ))
    net.add_branch(Branch(
        id="b3", from_node="split", to_node="faceA_in",
        name="District A Intake", length_m=400, base_resistance=0.06, area_m2=10,
        regulator=Regulator(ref_resistance=0.02, opening_pct=100.0),
    ))
    net.add_branch(Branch(
        id="b4", from_node="split", to_node="faceB_in",
        name="District B Intake", length_m=520, base_resistance=0.08, area_m2=10,
        regulator=Regulator(ref_resistance=0.02, opening_pct=100.0),
    ))
    net.add_branch(Branch(
        id="b5", from_node="faceA_in", to_node="faceA_out",
        name="District A Face (Continuous Miner)", length_m=60, base_resistance=0.12, area_m2=8,
        dust_source=DustSource(generation_rate=45.0, label="District A face"),
    ))
    net.add_branch(Branch(
        id="b6", from_node="faceB_in", to_node="faceB_out",
        name="District B Face (Continuous Miner)", length_m=60, base_resistance=0.16, area_m2=8,
        dust_source=DustSource(generation_rate=32.0, label="District B face"),
    ))
    net.add_branch(Branch(
        id="b7", from_node="faceA_out", to_node="return_junction",
        name="District A Return", length_m=430, base_resistance=0.05, area_m2=10,
    ))
    net.add_branch(Branch(
        id="b8", from_node="faceB_out", to_node="return_junction",
        name="District B Return", length_m=560, base_resistance=0.07, area_m2=10,
    ))
    net.add_branch(Branch(
        id="b9", from_node="return_junction", to_node="upcast_bottom",
        name="Main Return Roadway", length_m=250, base_resistance=0.025, area_m2=16,
    ))
    net.add_branch(Branch(
        id="b10", from_node="upcast_bottom", to_node="surface_out",
        name="Upcast Shaft (Main Fan)", length_m=180, base_resistance=0.018, area_m2=20,
        fan=Fan(shutoff_pressure=2800.0, curve_k=3.4, speed=1.0),
    ))
    # Virtual zero-resistance branch closing the circuit through the atmosphere:
    # air leaving the upcast (surface_out) and air entering the downcast
    # (surface_in) are both at the same barometric datum, so the full mine
    # circuit is a closed loop for Kirchhoff's pressure law.
    net.add_branch(Branch(
        id="b0_atm", from_node="surface_out", to_node="surface_in",
        name="Atmosphere (return-to-intake datum)", length_m=0, base_resistance=1e-6, area_m2=1e6,
        is_atmosphere=True,
    ))

    return net
