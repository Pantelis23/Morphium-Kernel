#!/usr/bin/env python3
"""
Morphium PRESSURE TESTS — physical-limit envelopes per device.
==============================================================
Different from stress_test.py (which drifts composition to test fab robustness).
This pushes each layer's CHAMPION against the *physical walls* — energy/bit,
density, retention, force, optical loss, and (system-level) heat-vs-size — to
answer "how far can it actually go?" and "what is the binding constraint?".

Every number is derived from the champion's simulated material metrics plus
standard device physics (constants below, with sources). HONEST: where the
kernel's metric is conservative vs the real material ceiling (e.g. IGZO Ioff is
floored in the model), both are shown. These are order-of-magnitude engineering
envelopes, not datasheet guarantees. See docs/DATA_PROVENANCE.md.

Usage:  python3 tools/pressure_test.py --root .
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.morphium_kernel.kernel import KernelClient
from sensitivity_analysis import extract_metrics, CHAMPIONS

# --- physics constants ---
Q = 1.602e-19          # C
EPS0 = 8.854e-12       # F/m
KB = 1.381e-23         # J/K
HC_EV_NM = 1240.0      # eV*nm

# --- engineering assumptions (stated, not hidden) ---
EC_HZO_MV_CM = 1.2     # HZO coercive field ~1-2 MV/cm (Mueller/Park)
T_E_NM = 10.0          # ferroelectric thickness (champion)
F_NODE_NM = 10.0       # assumed feature size for density
IGZO_IOFF_REAL = 1e-19 # real a-IGZO off-current ~1e-19-1e-22 A (model floors at ~1e-13)
LAMBDA_NM = 1550.0     # PM operating wavelength
H_CONV = 25.0          # W/m^2/K natural+slight-forced convection (phone-class)
DT_MAX = 40.0          # K case-surface rise above ambient (non-skin-contact; skin-worn wants ~15-25 K)


def _hdr(title):
    print(f"\n{'='*68}\n  {title}\n{'='*68}")


def pressure_E(m):
    _hdr("E (HfZrO2 ferroelectric) — non-volatile memory / logic")
    Pr = m.get("polarization_uC_cm2", 17.6) * 1e-2      # uC/cm2 -> C/m2
    Ec = EC_HZO_MV_CM * 1e8                              # MV/cm -> V/m
    t  = T_E_NM * 1e-9
    F  = F_NODE_NM * 1e-9
    # Switch energy/bit ~ 2*Pr*Ec*volume (area integral of E.dP over the loop)
    e_per_area = 2 * Pr * Ec * t                         # J/m^2
    e_bit = e_per_area * F * F                           # J
    dens = 1.0 / (F * F) / 1e4                           # bits/cm^2 (2D)
    endur = m.get("endurance_cycles", 1e10)
    print(f"  write energy/bit   : {e_bit*1e18:8.2f} aJ   (Pr={Pr:.3f} C/m2, Ec={EC_HZO_MV_CM} MV/cm, {F_NODE_NM}nm cell)")
    print(f"  areal density (2D) : {dens:8.2e} bit/cm2  ({F_NODE_NM}nm); 3D-stackable -> x(layers)")
    print(f"  endurance          : {endur:8.2e} cycles")
    print(f"  retention          : non-volatile (>10 yr) — no refresh power")
    print(f"  >> BINDING WALL    : ENDURANCE ({endur:.0e}) for write-heavy use (DRAM wants ~1e16);")
    print(f"     memory/inference (rare writes) is essentially unconstrained. Frontier:")
    print(f"     negative-capacitance gate -> sub-60mV/dec switching (below the Boltzmann floor).")


def pressure_L(m):
    _hdr("L (IGZO oxide TFT) — BEOL logic / capacitor-less DRAM")
    mu = m.get("mobility_cm2_Vs", 21.0)
    ioff_model = m.get("Ioff_A", 3e-13)
    C_cell = 1e-15      # ~1 fF storage node
    dV = 0.1            # tolerable droop
    Q_store = C_cell * dV
    ret_model = Q_store / ioff_model
    ret_real  = Q_store / IGZO_IOFF_REAL
    standby_model = ioff_model * 1.0    # W per cell at 1V (model)
    standby_real  = IGZO_IOFF_REAL * 1.0
    print(f"  mobility           : {mu:6.1f} cm2/Vs  (drive current / switching speed)")
    print(f"  retention (model)  : {ret_model*1e3:8.2e} ms   (Ioff_model={ioff_model:.1e} A — model is FLOORED)")
    print(f"  retention (real)   : {ret_real:8.2e} s   (Ioff_real~{IGZO_IOFF_REAL:.0e} A — a-IGZO's real edge)")
    print(f"  standby power/cell : {standby_real*1e21:8.2f} zW (real)  vs {standby_model*1e15:.1f} fW (model floor)")
    print(f"  >> BINDING WALL    : the mobility<->leakage tradeoff. IGZO's near-zero real Ioff")
    print(f"     buys seconds-hours DRAM retention + ~zero standby -> enables monolithic-3D")
    print(f"     logic-on-memory; the wall is THERMAL once you stack many layers (see system).")
    print(f"     NOTE: the model floors Ioff at ~1e-13 (conservative); real ceiling is far better.")


def pressure_PM(m):
    _hdr("PM (Sb2Se3 phase-change photonics) — non-volatile optical compute")
    dn = m.get("delta_n", 0.75)
    k  = m.get("loss_k", 5e-6)
    endur = m.get("cycling_endurance", 1e8)
    # absorption coeff alpha = 4*pi*k/lambda ; loss in dB/cm
    lam_m = LAMBDA_NM * 1e-9
    alpha = 4 * 3.14159 * k / lam_m                      # 1/m
    loss_dB_cm = alpha * (10/2.3026) * 1e-2              # dB/cm
    # insertion loss per switch (~lambda-scale interaction length, generous)
    L_switch_m = 5e-6
    il_dB = alpha * (10/2.3026) * L_switch_m
    cascade = 3.0 / max(il_dB, 1e-6)                     # switches before 3 dB budget
    print(f"  index contrast dn  : {dn:6.3f}   (phase shift per switch; high = compact)")
    print(f"  propagation loss   : {loss_dB_cm:8.3f} dB/cm  (k={k:.1e} @ {LAMBDA_NM:.0f}nm)")
    print(f"  loss / switch      : {il_dB*1e3:8.2f} mdB  (~5um interaction)")
    print(f"  cascade depth      : {cascade:8.0f} switches within a 3 dB budget")
    print(f"  reconfig endurance : {endur:8.2e} cycles (GEOMETRY-limited; nanostructured)")
    print(f"  >> BINDING WALL    : RECONFIG ENDURANCE ({endur:.0e}) — the photonic state wears")
    print(f"     out 100-1000x before the other layers. For a FIXED optical-AI weight set")
    print(f"     (write once, read at light-speed, zero static power) it is near-ideal;")
    print(f"     for a constantly-reshaping fabric it is the lifetime cap.")


def pressure_EM(m):
    _hdr("EM (ScAlN piezo) — actuation / the morphing engine")
    d33 = m.get("d33_pC_N", 22.0) * 1e-12               # pC/N = pm/V
    V = 40.0
    n_layers = 20
    lever = 50.0
    stroke_um = d33 * V * n_layers * lever * 1e6        # m -> um
    # blocked force ~ d33 * E_field * area * Y (rough)
    E_field = V / (1e-6)                                 # 1um actuator
    Y = m.get("youngs_modulus_GPa", 260.0) * 1e9
    area = (50e-6)**2
    force_mN = d33 * E_field * Y * area * 1e3
    e_act = 0.5 * (EPS0 * 10 * area / 1e-6) * V**2       # ~0.5 C V^2
    print(f"  d33                : {d33*1e12:6.1f} pm/V")
    print(f"  stroke (amplified) : {stroke_um:8.3f} um  (V={V}, {n_layers}-layer x {lever:.0f} lever)")
    print(f"  blocked force      : {force_mN:8.3f} mN  (50um actuator)")
    print(f"  actuation energy   : {e_act*1e12:8.2f} pJ / stroke")
    print(f"  >> BINDING WALL    : DIELECTRIC BREAKDOWN — d33 rises with Sc, but breakdown")
    print(f"     field FALLS (6.5->5.9 MV/cm over 22->36% Sc) and rock-salt AOGs nucleate")
    print(f"     ~30-35% Sc. So usable stroke is capped by 'how hard can you drive before")
    print(f"     it leaks/cracks', not by d33 alone. Sub-coercive piezo is ~fatigue-free (>=1e12).")


def pressure_system(em_force_mN):
    _hdr("SYSTEM — the heat-vs-size wall (the real ceiling on 'computational matter')")
    # Max dissipated power a passively-cooled object can shed: P = h * A * dT
    for name, r_cm in [("watch (2cm)", 1.0), ("phone (7cm)", 3.5), ("umbrella (50cm)", 25.0)]:
        A = 4 * 3.14159 * (r_cm*1e-2)**2                 # sphere area, m^2
        P_max = H_CONV * A * DT_MAX                       # W
        vol_cm3 = (4/3)*3.14159*r_cm**3
        pdens = P_max / max(vol_cm3, 1e-9)               # W/cm^3
        print(f"  {name:16}: sheds {P_max*1e3:8.1f} mW total  -> {pdens*1e3:7.2f} mW/cm3 budget")
    print(f"  (h={H_CONV} W/m2K passive [optimistic; still-air ~5-10], dT={DT_MAX}K case-rise.)")
    print(f"  >> THE WALL: an object dissipates in its VOLUME but cools through its SURFACE")
    print(f"     (P_cool ~ r^2, P_gen ~ r^3) -> power density falls as 1/r. A watch can run")
    print(f"     ~mW/cm3; a phone less; an umbrella-sized compute brick would COOK itself.")
    print(f"     => 'be anything' is bounded by heat: small+cool or large+passive, not both.")
    print(f"  NOTE: this models each object as a SPHERE (worst-case 'folded into a blob') to")
    print(f"     expose the 1/r wall. Real Morphium devices are thin face-cooled SLABS that")
    print(f"     escape it (budget ~1/thickness) -> see tools/devices.py / docs/DEVICES.md, where")
    print(f"     the same phone is ~292 mW/cm3 (slab) vs {12.0:.0f}-86 mW/cm3 here (sphere). Not a")
    print(f"     contradiction: slab = the device, sphere = the pathological fold.")
    # foglet count + reconfig budget for a phone-sized object
    fog_um = 100.0
    fog_vol = (fog_um*1e-4)**3                            # cm^3
    N = (4/3)*3.14159*3.5**3 / fog_vol
    print(f"\n  Programmable-matter budget (100um foglets, phone-sized object):")
    print(f"    foglet count     : {N:8.2e}   (granularity floor ~1-10um -> finer needs ~1e12+)")
    print(f"    >> reconfiguration energy + time scale with N; 'phone->umbrella' is a real")
    print(f"       power/time budget, not instant. This + heat are the moonshot's hard walls.")


def main():
    ap = argparse.ArgumentParser(description="Morphium physical-limit pressure tests")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    kc = KernelClient(project_root=args.root)

    def metrics(layer):
        r = kc.simulate(layer, CHAMPIONS[layer], seed=42)
        return extract_metrics(layer, r) if layer != "E" else r.get("data", r.get("metrics", {}))

    mE  = kc.simulate("E", CHAMPIONS["E"], seed=42).get("data", {})
    mL  = extract_metrics("L", kc.simulate("L", CHAMPIONS["L"], seed=42))
    # Stored CHAMPIONS['PM'] is a degenerate placeholder (Ge=Cl=1, over-doped);
    # use a representative search-class champion at its endurance ceiling.
    pm_state = {"formula": "Sb2:Se3:Ge0.07:Cl0.1", "integration": "nanostructured", "seed": 42}
    mPM = extract_metrics("PM", kc.simulate("PM", pm_state, seed=42))
    mEM = extract_metrics("EM", kc.simulate("EM", CHAMPIONS["EM"], seed=42))

    print("MORPHIUM PRESSURE TESTS — physical-limit envelopes (champion-derived).")
    pressure_E(mE)
    pressure_L(mL)
    pressure_PM(mPM)
    pressure_EM(mEM)
    pressure_system(mEM.get("d33_pC_N", 22.0))
    print(f"\n{'='*68}\n  Run `--root .`; numbers are order-of-magnitude engineering envelopes.")


if __name__ == "__main__":
    main()
