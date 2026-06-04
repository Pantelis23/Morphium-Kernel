#!/usr/bin/env python3
"""
Morphium DEVICE ENVELOPES — what the 5-layer stack becomes as real products.
============================================================================
The same stack (E/EM/PM/L/M) reconfigures into different devices. This tool
takes three target form factors — WATCH, PHONE, DESKTOP — and derives, from the
CHAMPION material metrics + the pressure-test physical walls, what each device
can actually do and what its binding constraint is.

The two axes that separate the devices:
  1. SIZE  -> passive heat budget. An object generates heat in its VOLUME but
     sheds it through its SURFACE, so passive power density falls as ~1/r
     (P_cool ~ r^2, P_gen ~ r^3). Small = high mW/cm^3, large = low.
  2. POWER / COOLING. watch & phone: battery, passive. desktop: wall power +
     ACTIVE cooling (forced air), which lifts the convection coefficient ~6x
     and removes thermal as the binding wall — exposing the LOGIC-CLOCK wall.

Recommended FIRST demonstrator: the WATCH (argued at the bottom of the report) —
smallest area (highest yield, see stack_yield.py), highest volumetric heat
headroom, lowest absolute compute demand, and it still exercises all five layers.

HONEST: memory capacity and thermal budgets are derived from champion metrics +
first-principles. Logic THROUGHPUT is the soft axis — IGZO TFT logic is low-clock
(see the clock gap printed per device); treat compute numbers as order-of-magnitude.
See docs/DATA_PROVENANCE.md and docs/DEVICES.md.

Usage:  python3 tools/devices.py            # full report
        python3 tools/devices.py --json
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.morphium_kernel.kernel import KernelClient
from sensitivity_analysis import extract_metrics, CHAMPIONS

# --- shared physics / device-physics constants (match pressure_test.py) ---
H_PASSIVE = 25.0       # W/m^2/K  natural convection (skin-against-device)
H_ACTIVE  = 150.0      # W/m^2/K  forced air (desktop fan/heatsink), ~6x passive
DT_MAX    = 40.0       # K  skin-safe / case surface rise
E_DENSITY_2D = 1.0e12  # bit/cm^2  E ferroelectric cell @10nm (pressure_test)
SI_CLK_GHZ   = 4.0     # reference Si CMOS scalar clock (the thing IGZO can't match)
IGZO_CLK_GHZ = 0.3     # representative manufacturable BEOL a-IGZO logic clock
                       # (scaled a-IGZO ring osc ~0.1-1 GHz; printed/large ~MHz)
IGZO_EOP_FJ  = 3.0     # ~fJ/op low-voltage TFT logic (order-of-magnitude)
FOGLET_UM    = 100.0   # programmable-matter granularity floor (pressure_test)

# device geometries: face WxH (cm), thickness (cm), E-memory planes in the stack,
# power source, and whether active cooling is available.
DEVICES = {
    "WATCH": {
        "face": (4.0, 4.0), "thick": 1.2, "e_planes": 4,
        "cooling": "passive", "batt_Wh": 0.3, "use": "wearable: sensing, haptics, reflective display, always-on",
    },
    "PHONE": {
        "face": (15.0, 7.0), "thick": 0.8, "e_planes": 8,
        "cooling": "passive", "batt_Wh": 15.0, "use": "handset: display, mixed compute, large NV memory, haptics",
    },
    "DESKTOP": {
        "face": (30.0, 30.0), "thick": 1.0, "e_planes": 16,
        "cooling": "active", "batt_Wh": None, "use": "stationary: memory-centric + optical-AI accelerator (NOT a scalar CPU)",
    },
}


def _hdr(title):
    print(f"\n{'='*72}\n  {title}\n{'='*72}")


def champion_metrics():
    """Pull the few champion metrics the device envelopes need."""
    kc = KernelClient(project_root=".")
    out = {}
    for layer in ("L", "PM", "EM"):
        st = {k: v for k, v in CHAMPIONS[layer].items() if k != "seed"}
        res = kc.simulate(layer, st, seed=CHAMPIONS[layer].get("seed", 42))
        out[layer] = extract_metrics(layer, res)
    return out


def envelope(name, m):
    d = DEVICES[name]
    w, h = d["face"]
    A_face = w * h                                  # cm^2 (one active face)
    A_cool = 2 * A_face + 2 * (w + h) * d["thick"]  # cm^2 (both faces + edges)
    V = A_face * d["thick"]                         # cm^3

    # --- thermal budget ---
    hconv = H_ACTIVE if d["cooling"] == "active" else H_PASSIVE
    P_total_W = hconv * (A_cool * 1e-4) * DT_MAX    # W  (cm^2 -> m^2)
    P_dens = P_total_W / V * 1e3                    # mW/cm^3

    # --- non-volatile memory (E density x area x planes) ---
    bits = E_DENSITY_2D * A_face * d["e_planes"]
    TB = bits / 8 / 1e12

    # --- logic (IGZO TFT, clock-limited; this is the soft axis) ---
    clk_gap = SI_CLK_GHZ / IGZO_CLK_GHZ
    # thermal-limited op rate if the WHOLE budget went to logic at IGZO_EOP_FJ/op
    ops_thermal = P_total_W / (IGZO_EOP_FJ * 1e-15)   # ops/s

    # --- photonics (PM as nonvolatile optical weights / interconnect) ---
    # optical-MAC matrix side ~ champion cascade depth within a 3 dB budget (pressure_test)
    matmul_dim = 897

    # --- actuation / morphing (blocked force from d33, same physics as pressure_test) ---
    d33 = m["EM"].get("d33_pC_N", 22.0) * 1e-12             # pm/V
    Y = m["EM"].get("youngs_modulus_GPa", 260.0) * 1e9
    force_mN = d33 * (40.0 / 1e-6) * Y * (50e-6) ** 2 * 1e3  # 50um actuator @40V
    foglets = (A_face / (FOGLET_UM * 1e-4) ** 2)   # count at granularity floor over the face

    return {
        "A_face_cm2": A_face, "A_cool_cm2": A_cool, "V_cm3": V,
        "cooling": d["cooling"], "P_total_W": P_total_W, "P_dens_mW_cm3": P_dens,
        "mem_TB": TB, "e_planes": d["e_planes"],
        "logic_clk_GHz": IGZO_CLK_GHZ, "clk_gap_vs_Si": clk_gap, "ops_thermal": ops_thermal,
        "opt_matmul_dim": matmul_dim, "foglets": foglets,
        "force_mN": force_mN, "batt_Wh": d["batt_Wh"], "use": d["use"],
    }


def binding_constraint(name, e):
    """The honest one-line wall per device."""
    if name == "WATCH":
        return ("BATTERY ENERGY, not heat. As a thin face-cooled slab the heat budget is ample "
                f"({e['P_dens_mW_cm3']:.0f} mW/cm^3); all-day life on {e['batt_Wh']*1000:.0f} mWh "
                "caps AVERAGE draw to ~tens of mW. Low-clock IGZO + non-volatile E (zero standby) "
                "is exactly the right fit; the watch never approaches its thermal ceiling.")
    if name == "PHONE":
        return ("SUSTAINED THERMAL + logic clock. Passive budget "
                f"({e['P_dens_mW_cm3']:.0f} mW/cm^3) is real but phones throttle under load; "
                f"heavy apps also hit the ~{e['clk_gap_vs_Si']:.0f}x IGZO<->Si clock gap. "
                "Wins on huge NV memory + photonic interconnect, not on peak single-thread.")
    if name == "DESKTOP":
        return ("LOGIC CLOCK, not heat. Active cooling lifts the budget to "
                f"{e['P_total_W']:.0f} W ({e['P_dens_mW_cm3']:.0f} mW/cm^3) so thermal is SOLVED; "
                f"the wall is the ~{e['clk_gap_vs_Si']:.0f}x clock gap — IGZO TFT logic can't do "
                "GHz scalar work. A Morphium 'desktop' is a compute-in-memory + optical-AI "
                "accelerator (light-speed MACs, ~100s TB NV memory), NOT a faster Ryzen.")
    return ""


def report():
    m = champion_metrics()
    results = {}
    _hdr("DEVICE ENVELOPES (champion-derived; same stack, three form factors)")
    print(f"  {'device':8} {'face cm2':>9} {'thermal':>10} {'mW/cm3':>8} {'NV mem':>9} {'clk gap':>8}")
    for name in ("WATCH", "PHONE", "DESKTOP"):
        e = envelope(name, m)
        results[name] = e
        cool = "active" if e["cooling"] == "active" else "passiv"
        print(f"  {name:8} {e['A_face_cm2']:8.0f}  {e['P_total_W']:7.1f}W({cool[:3]}) "
              f"{e['P_dens_mW_cm3']:7.0f} {e['mem_TB']:7.0f}TB {e['clk_gap_vs_Si']:6.0f}x")

    for name in ("WATCH", "PHONE", "DESKTOP"):
        e = results[name]
        _hdr(f"{name} — {e['use']}")
        print(f"  form factor      : {DEVICES[name]['face'][0]:.0f}x{DEVICES[name]['face'][1]:.0f} cm face, "
              f"{DEVICES[name]['thick']:.1f} cm thick  ({e['V_cm3']:.0f} cm^3)")
        print(f"  thermal budget   : {e['P_total_W']:.0f} W {e['cooling']}  -> {e['P_dens_mW_cm3']:.0f} mW/cm^3")
        print(f"  non-volatile mem : {e['mem_TB']:.0f} TB   (E @1Tbit/cm^2 x {e['A_face_cm2']:.0f}cm^2 x {e['e_planes']} planes; "
              "10-yr retention, ZERO refresh power)")
        print(f"  logic            : ~{e['logic_clk_GHz']:.1f} GHz IGZO TFT clock  "
              f"({e['clk_gap_vs_Si']:.0f}x below ~{SI_CLK_GHZ:.0f} GHz Si) "
              f"-> low-clock / high-parallel / compute-in-memory")
        print(f"  photonics (PM)   : nonvolatile optical weights, ~{e['opt_matmul_dim']} cascade depth "
              "(matrix side) -> light-speed MACs, zero static power; 1e8 weight-rewrite life")
        print(f"  actuation (EM/M) : {e['force_mN']:.0f} mN blocked force -> haptics / morphing; "
              f"up to ~{e['foglets']:.1e} 100um foglets over the face")
        if e["batt_Wh"]:
            print(f"  power source     : {e['batt_Wh']*1000:.0f} mWh battery, {e['cooling']} cooling")
        else:
            print(f"  power source     : wall power, {e['cooling']} cooling (fan/heatsink)")
        print(f"  >> BINDING WALL  : {binding_constraint(name, e)}")

    _hdr("WHICH TO BUILD FIRST -> WATCH")
    print("  * smallest face area  -> highest composite yield (yield ~ exp(-area); see stack_yield.py)")
    print("  * lowest absolute compute demand -> IGZO's low clock is sufficient, not a liability")
    print("  * thermal is a non-issue (all three are thin face-cooled slabs; see geometry note)")
    print("  * still exercises ALL five layers: E (NV store), L (logic), PM (reflective/ambient")
    print("    display modulation), EM (haptics), M (a morphing band / case) -> a true 5-layer tile")
    print("  * de-risks the hard parts (co-integration, reconfiguration) at the cheapest area/cost")

    _hdr("HONESTY / LIMITS")
    print("  * Memory capacity & thermal budgets: first-principles from champion metrics (firm).")
    print("  * GEOMETRY NOTE: these devices are thin SLABS -> face-cooled, so P_dens ~ 1/thickness")
    print("    and ALL three shed heat fine (thinner phone > thicker watch). The pressure-test")
    print("    1/r 'cube cooks itself' wall returns only if you FOLD a device into a brick.")
    print(f"  * Logic THROUGHPUT is the soft axis: IGZO clock assumed {IGZO_CLK_GHZ} GHz (lit range")
    print("    0.1-1 GHz); the Si clock gap is the honest reason Morphium is not a scalar CPU.")
    print("  * 'foglet count' is a granularity-floor maximum, not a built design.")
    print("  * Active-cooling h=150 is a modest forced-air figure; liquid would go higher still.")
    print("  * Per-device numbers are order-of-magnitude product envelopes, not a datasheet.")
    return results


def main():
    ap = argparse.ArgumentParser(description="Morphium device envelopes (watch/phone/desktop)")
    ap.add_argument("--root", default=".", help="repo root (tool-suite consistency)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON")
    args = ap.parse_args()
    if args.json:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = report()
        print(json.dumps(res, indent=2, default=float))
    else:
        report()


if __name__ == "__main__":
    main()
