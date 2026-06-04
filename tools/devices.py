#!/usr/bin/env python3
"""
Morphium DEVICE ENVELOPES — what the 5-layer stack becomes as real products.
============================================================================
The same stack (E/EM/PM/L/M) reconfigures into different devices. This tool
takes three target form factors — WATCH, PHONE, DESKTOP — and derives, from the
CHAMPION material metrics + the pressure-test physical walls, what each device
can actually do and what its binding constraint is.

The two axes that separate the devices:
  1. SIZE  -> passive heat budget (thin face-cooled slab: ~1/thickness) AND
     monolithic yield (defects ~ exp(-area) -> small wins big).
  2. POWER / COOLING. watch & phone: battery, passive. desktop: wall power +
     active cooling, which removes thermal as the wall and exposes the LOGIC clock.

Recommended FIRST demonstrator: the WATCH — smallest face area gives by far the
highest monolithic yield (computed below), lowest absolute compute demand, and it
still exercises all five layers.

HONESTY (this tool was adversarially audited 2026-06-04; see docs/AUDIT_2026-06-04.md):
  * Memory density and IGZO logic clock are reported as TWO numbers — a demonstrated
    figure (honest near-term) and a theoretical/projected ceiling (roadmap). Earlier
    versions printed only the ceiling and were optimistic by ~100x (density) and
    ~30-400x (clock).
  * Plane counts (4/8/16) are a SPECULATIVE roadmap multiplier; the thermal budget
    (integration.py) only supports ~2-4 co-integrated E planes today. Capacities are
    order-of-magnitude, NOT firm.
  * Thermal h and dT are optimistic ceilings (see comments); the watch's real wall is
    battery, so heat never binds it.
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

# --- thermal constants (OPTIMISTIC ceilings; read budgets as upper bounds) ---
H_PASSIVE = 25.0       # W/m^2/K  natural convection. OPTIMISTIC: realistic still air ~5-10.
H_ACTIVE  = 150.0      # W/m^2/K  forced air. OPTIMISTIC for a BARE slab (needs ~40 m/s or a
                       # finned heatsink); a realistic bare-slab fan figure is ~25-50 -> 300-600 W.
DT_MAX    = 40.0       # K  CASE-surface rise above ambient (non-skin-contact). NOT skin-safe for a
                       # worn device: continuous skin contact wants ~15-25 K (IEC 60601-1 ~43 C).

# --- memory: report demonstrated AND theoretical-ceiling density ---
E_DENSITY_DEMO = 1.0e10  # bit/cm^2  demonstrated FeFET/FeRAM single-plane areal density
E_DENSITY_CEIL = 1.0e12  # bit/cm^2  1F^2 lithographic ceiling at the ~10nm ferroelectric scaling
                         # limit (NOT an achievable cell density)

# --- logic: IGZO TFT is the soft axis -> measured vs projected clock ---
IGZO_CLK_MEAS_GHZ = 0.01   # ~10 MHz  measured a-IGZO logic / ring-osc (large-geometry BEOL)
IGZO_CLK_PROJ_GHZ = 0.2    # ~0.2 GHz aggressive SCALED-node projection (not yet manufacturable)
SI_CLK_GHZ        = 4.0    # reference Si CMOS scalar clock
IGZO_EOP_FJ       = 3.0    # fJ/op scaled-node FLOOR (audit-defended as order-of-magnitude);
                           # realistic DEMONSTRATED TFT logic is ~0.1-1 pJ/op (~100-1000x higher)

# --- monolithic yield: defect-limited, area-driven (the watch-first lever) ---
D0_PER_CM2   = 0.05    # defects/cm^2 PER LAYER (optimistic research-grade; illustrative)
N_CRIT_LAYERS = 5      # all five layers must be defect-free in a cell

# --- photonics / morphing ---
PM_CASCADE   = 897     # champion cascade depth within 3 dB (pressure_test) — a PROPAGATION/SNR
                       # limit, NOT a MAC matrix dimension (see note in report)
FOGLET_UM    = 100.0   # programmable-matter granularity floor (pressure_test)

# device geometries: face WxH (cm), thickness (cm), E-memory planes (SPECULATIVE), power, cooling.
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


def _cap_str(bits):
    """bits -> human capacity string."""
    by = bits / 8
    for unit, scale in (("PB", 1e15), ("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if by >= scale:
            return f"{by/scale:.0f} {unit}"
    return f"{by:.0f} B"


def champion_metrics():
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

    # --- thermal budget (optimistic ceiling) ---
    hconv = H_ACTIVE if d["cooling"] == "active" else H_PASSIVE
    P_total_W = hconv * (A_cool * 1e-4) * DT_MAX
    P_dens = P_total_W / V * 1e3                    # mW/cm^3

    # --- non-volatile memory: demonstrated vs ceiling, x planes ---
    bits_demo = E_DENSITY_DEMO * A_face * d["e_planes"]
    bits_ceil = E_DENSITY_CEIL * A_face * d["e_planes"]

    # --- logic clock gap (report measured AND projected) ---
    gap_meas = SI_CLK_GHZ / IGZO_CLK_MEAS_GHZ      # ~400x
    gap_proj = SI_CLK_GHZ / IGZO_CLK_PROJ_GHZ      # ~20x

    # --- monolithic yield (defect-limited; the watch-first lever) ---
    Y_area = 2.718281828 ** (-(A_face * D0_PER_CM2 * N_CRIT_LAYERS))

    # --- actuation (blocked force from champion d33, same physics as pressure_test) ---
    d33 = m["EM"].get("d33_pC_N", 22.0) * 1e-12
    Y = m["EM"].get("youngs_modulus_GPa", 260.0) * 1e9
    force_mN = d33 * (40.0 / 1e-6) * Y * (50e-6) ** 2 * 1e3
    foglets = (A_face / (FOGLET_UM * 1e-4) ** 2)

    return {
        "A_face_cm2": A_face, "A_cool_cm2": A_cool, "V_cm3": V,
        "cooling": d["cooling"], "P_total_W": P_total_W, "P_dens_mW_cm3": P_dens,
        "mem_demo": _cap_str(bits_demo), "mem_ceil": _cap_str(bits_ceil), "e_planes": d["e_planes"],
        "clk_gap_meas": gap_meas, "clk_gap_proj": gap_proj, "yield_pct": Y_area * 100.0,
        "force_mN": force_mN, "foglets": foglets, "batt_Wh": d["batt_Wh"], "use": d["use"],
    }


def binding_constraint(name, e):
    if name == "WATCH":
        return ("BATTERY ENERGY, not heat. As a thin face-cooled slab the heat budget is ample "
                f"(~{e['P_total_W']:.0f} W ceiling); all-day life on {e['batt_Wh']*1000:.0f} mWh "
                "caps AVERAGE draw to ~tens of mW. Low-clock IGZO + non-volatile E (zero hold power) "
                "is exactly the right fit. It is also the ONLY form factor with a workable single-die "
                "monolithic yield (still modest -> wants redundancy/tiling, but orders above phone/desktop).")
    if name == "PHONE":
        return ("SUSTAINED THERMAL + logic clock. Passive budget is real but phones throttle under "
                f"load; heavy apps hit the IGZO<->Si clock gap (~{e['clk_gap_proj']:.0f}x projected, "
                f"~{e['clk_gap_meas']:.0f}x at today's measured TFT speeds). Wins on NV memory + "
                "photonic interconnect, not peak single-thread. Yield needs tiling at this area.")
    if name == "DESKTOP":
        return ("LOGIC CLOCK + MONOLITHIC YIELD, not heat. Active cooling (optimistically ~1 kW, "
                f"realistically ~300-600 W bare-slab) takes thermal off the table; the walls are the "
                f"~{e['clk_gap_meas']:.0f}x measured clock gap and a monolithic yield of ~{e['yield_pct']:.0e}% "
                "at 900 cm^2 -> a desktop MUST be TILED from small dies, not one slab. A Morphium "
                "'desktop' is a compute-in-memory + optical-AI accelerator, NOT a faster Ryzen.")
    return ""


def report():
    m = champion_metrics()
    results = {}
    _hdr("DEVICE ENVELOPES (champion-derived; same stack, three form factors)")
    print(f"  {'device':8} {'face cm2':>9} {'heat (ceil)':>12} {'NV mem (demo)':>14} {'clk gap':>10} {'mono-yield':>11}")
    for name in ("WATCH", "PHONE", "DESKTOP"):
        e = envelope(name, m)
        results[name] = e
        cool = "act" if e["cooling"] == "active" else "pas"
        print(f"  {name:8} {e['A_face_cm2']:8.0f}  {e['P_total_W']:8.0f}W({cool}) {e['mem_demo']:>14} "
              f"{e['clk_gap_meas']:8.0f}x  {e['yield_pct']:9.1e}%")

    for name in ("WATCH", "PHONE", "DESKTOP"):
        e = results[name]
        _hdr(f"{name} — {e['use']}")
        print(f"  form factor      : {DEVICES[name]['face'][0]:.0f}x{DEVICES[name]['face'][1]:.0f} cm face, "
              f"{DEVICES[name]['thick']:.1f} cm thick  ({e['V_cm3']:.0f} cm^3)")
        print(f"  thermal budget   : ~{e['P_total_W']:.0f} W {e['cooling']} (optimistic ceiling) "
              f"-> {e['P_dens_mW_cm3']:.0f} mW/cm^3")
        print(f"  non-volatile mem : ~{e['mem_demo']} demonstrated  ({e['mem_ceil']} at the 1F^2 ceiling) "
              f"-- E @ {E_DENSITY_DEMO:.0e} bit/cm^2 x {e['A_face_cm2']:.0f}cm^2 x {e['e_planes']} planes (planes SPECULATIVE)")
        print(f"  logic            : ~{IGZO_CLK_MEAS_GHZ*1e3:.0f} MHz measured IGZO TFT "
              f"(~{IGZO_CLK_PROJ_GHZ*1e3:.0f} MHz projected scaled); {e['clk_gap_meas']:.0f}x below "
              f"{SI_CLK_GHZ:.0f} GHz Si -> low-clock / parallel / compute-in-memory, NOT scalar-fast")
        print(f"  photonics (PM)   : nonvolatile optical weights; cascade depth ~{PM_CASCADE} is a "
              "PROPAGATION limit (coherent-mesh matrix side <=~448 intrinsic, ~tens with real")
        print(f"                     per-modulator loss). Zero static HOLD power; 1e8 weight-rewrite life")
        print(f"  actuation (EM/M) : {e['force_mN']:.0f} mN blocked force -> haptics / morphing; "
              f"up to ~{e['foglets']:.1e} 100um foglets over the face")
        print(f"  monolithic yield : ~{e['yield_pct']:.1e} %  (defect ~exp(-area), D0={D0_PER_CM2}/cm^2/layer x 5 layers; illustrative)")
        if e["batt_Wh"]:
            print(f"  power source     : {e['batt_Wh']*1000:.0f} mWh battery, {e['cooling']} cooling")
        else:
            print(f"  power source     : wall power, {e['cooling']} cooling (fan/heatsink)")
        print(f"  >> BINDING WALL  : {binding_constraint(name, e)}")

    _hdr("WHICH TO BUILD FIRST -> WATCH (now computed, not asserted)")
    yw, yp, yd = results["WATCH"]["yield_pct"], results["PHONE"]["yield_pct"], results["DESKTOP"]["yield_pct"]
    print(f"  * monolithic yield falls steeply with area: watch ~{yw:.1e}% >> phone ~{yp:.1e}% >> desktop ~{yd:.1e}%")
    print("    -> the desktop is UN-yieldable as one slab (must be tiled); the watch is the only")
    print("       form factor with a sane single-die monolithic yield. This is the dominant reason.")
    print("  * lowest absolute compute demand -> IGZO's low clock is sufficient, not a liability")
    print("  * thermal is a non-issue (all three are thin face-cooled slabs)")
    print("  * still exercises ALL five layers: E (NV store), L (logic), PM (reflective display),")
    print("    EM (haptics), M (a morphing band/case) -> a true 5-layer tile at the cheapest area")

    _hdr("HONESTY / LIMITS  (post-audit 2026-06-04)")
    print("  * Memory: DEMONSTRATED density 1e10 bit/cm^2 shown as headline; 1e12 (1F^2) is a")
    print("    theoretical ceiling. Plane counts 4/8/16 are a SPECULATIVE roadmap — the thermal")
    print("    budget (integration.py) supports ~2-4 monolithic E planes today, so high-plane")
    print("    capacities are order-of-magnitude, NOT firm, and NOT yet reconciled with integration.")
    print("  * Logic: ~10 MHz is the honest measured IGZO clock; 0.2 GHz is a scaled PROJECTION.")
    print("    Energy/op 3 fJ is a scaled-node floor (realistic demonstrated ~0.1-1 pJ/op).")
    print("  * Thermal h (25/150) and dT (40 K case-rise) are optimistic ceilings; skin-worn dT ~15-25 K.")
    print("  * Optical 'matrix side' is NOT the cascade depth; static power excludes lasers/detectors/ADC.")
    print("  * Yield D0 is illustrative; foglet counts are granularity-floor maxima, not built designs.")
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
