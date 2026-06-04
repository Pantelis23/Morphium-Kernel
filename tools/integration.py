#!/usr/bin/env python3
"""
Morphium INTEGRATION / THERMAL-BUDGET feasibility model.
========================================================
The per-layer pressure tests (pressure_test.py) ask "how far can ONE layer go?".
This asks the orthogonal monolithic-integration question: "can the five layers be
built into ONE stack at all, and in what order?"

Monolithic co-integration is governed by the descending-thermal-budget rule:
each fabrication step heats the WHOLE stack to its process temperature, so every
already-built layer must SURVIVE every later layer's process temperature. The
classic move is "build hottest-first" — but architectural position (e.g. M, the
foglet/programmable-matter layer, must be on top) can fight the thermal order.
This tool finds the orderings that satisfy both.

Two temperatures per layer:
  * T_process  — the temperature its fabrication actually requires (anneal /
                 deposition / crystallisation). Pulled LIVE from the current
                 champions where the kernel exposes it (E anneal, EM dep_temp);
                 from materials literature otherwise (L, PM, M).
  * T_survive  — the highest temperature the FINISHED layer tolerates before it
                 degrades (phase relaxation, dewetting, Se loss, crystallisation).
                 Materials-physics estimates; each tagged with a confidence.

HONEST: T_survive values are engineering estimates from the cited literature,
not in-house TGA/anneal-ladder data. They set order-of-magnitude integration
windows, not a qualified process flow. See docs/DATA_PROVENANCE.md.

Usage:  python3 tools/integration.py            # full report
        python3 tools/integration.py --json      # machine-readable
"""
import sys
import os
import json
import argparse
from itertools import permutations

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sensitivity_analysis import CHAMPIONS

# --- champion process temps (live from CHAMPIONS where exposed) ---
E_ANNEAL  = float(CHAMPIONS["E"].get("anneal_temp_C", 450.0))   # champion 559 C
EM_DEP    = float(CHAMPIONS["EM"].get("dep_temp_C", 350.0))     # champion 490 C

# Layers, in physical bottom->top architectural stack order (for reference only;
# the tool searches all orders). Each: process temp, survive temp, sources.
#   conf: how firm the T_survive estimate is (firm / est / soft).
LAYERS = {
    "E": {
        "name": "HfZrO2 ferroelectric (logic / non-volatile memory)",
        "T_process": E_ANNEAL,
        "T_survive": 600.0, "conf": "est",
        "proc_src": "anneal_temp_C from champion E (orthorhombic crystallisation sigmoid, onset 350 C)",
        "surv_src": "HZO orthorhombic phase relaxes toward monoclinic / loses 2Pr with prolonged T>~600-700 C "
                    "(Park 2015 Adv. Mater.; Materano 2020). 600 C taken as a conservative degradation onset.",
    },
    "EM": {
        "name": "ScAlN piezo actuation",
        "T_process": EM_DEP,
        "T_survive": 800.0, "conf": "firm",
        "proc_src": "dep_temp_C from champion EM (reactive-sputter texture sigmoid; >450 C raises ScN 2nd phase)",
        "surv_src": "Wurtzite Sc(Al)N is refractory; AlN stable >1000 C, ScAlN decomposition / rocksalt onset "
                    ">~800-900 C (Fichtner 2019; Casamento 2022). 800 C conservative.",
    },
    "L": {
        "name": "IGZO oxide TFT logic",
        "T_process": 350.0, "conf_proc": "est",
        "T_survive": 450.0, "conf": "est",
        "proc_src": "a-IGZO BEOL anneal ~300-400 C (Nomura/Hosono; Kamiya 2010 STAM). 350 C representative "
                    "(no temp knob in the L contract; channel composition is the searched DOF).",
        "surv_src": "a-IGZO crystallises / loses oxygen and Vth-shifts above ~400-500 C (Kamiya 2010; "
                    "Fortunato 2012). 450 C degradation onset.",
    },
    "PM": {
        "name": "Sb2Se3 phase-change photonics",
        "T_process": 200.0, "conf_proc": "est",
        "T_survive": 250.0, "conf": "firm",
        "proc_src": "Sb2Se3 amorphous->crystalline crystallisation ~180-200 C (Delaney 2020; Dong 2019). "
                    "200 C representative (set/crystallise step).",
        "surv_src": "BINDING WALL. Sb2Se3 films dewet/agglomerate and lose Se (Se volatile) and phase-change "
                    "contrast above ~250-300 C; any later >300 C step re-melts the set phase "
                    "(Delaney 2021 Sci. Adv.; Rios 2022). 250 C taken as the survival ceiling.",
    },
    "M": {
        "name": "HfO2:DLC foglets / programmable matter",
        "T_process": 120.0, "conf_proc": "soft",
        "T_survive": 250.0, "conf": "soft",
        "proc_src": "Foglet assembly / DLC + organic-binder cure is a low-T back-end step (~100-150 C). "
                    "120 C representative; M is a composite assembled, not annealed.",
        "surv_src": "DLC graphitises ~400-600 C but organic binders / electrostatic latch dielectrics "
                    "degrade ~200-300 C. 250 C; M is the top layer so this rarely binds.",
    },
}

# Architectural hard constraint: M (programmable-matter / foglet) layer must be on
# TOP — it requires E/EM/PM beneath it (composite M depends on them). So M is built
# LAST. Everything else is architecturally flexible; the thermal budget decides.
ARCH_LAST = "M"


def _hdr(title):
    print(f"\n{'='*70}\n  {title}\n{'='*70}")


def conflict_matrix():
    """A 'cannot be below' B  iff  T_process(B) > T_survive(A).
    (Building B after A heats the finished A to B's process temp.)"""
    keys = list(LAYERS)
    conflicts = {}  # (A,B): margin_deficit  (A built before B is INFEASIBLE)
    for a in keys:
        for b in keys:
            if a == b:
                continue
            if LAYERS[b]["T_process"] > LAYERS[a]["T_survive"]:
                conflicts[(a, b)] = LAYERS[b]["T_process"] - LAYERS[a]["T_survive"]
    return conflicts


def order_feasible(order):
    """order = build sequence (index 0 built first / bottom).
    Feasible iff each layer survives the max process temp of all LATER builds.
    Returns (ok, [(layer, max_later_Tproc, margin)])."""
    rows = []
    ok = True
    for i, lyr in enumerate(order):
        later = order[i + 1:]
        max_later = max((LAYERS[x]["T_process"] for x in later), default=0.0)
        margin = LAYERS[lyr]["T_survive"] - max_later
        if later and margin < 0:
            ok = False
        rows.append((lyr, max_later, margin))
    return ok, rows


def analyse():
    keys = list(LAYERS)

    _hdr("LAYER THERMAL WINDOWS (process temp it needs / temp it survives)")
    print(f"  {'layer':5} {'T_process':>10} {'T_survive':>10}  {'window':>8}  conf   description")
    for k in keys:
        L = LAYERS[k]
        win = L["T_survive"] - L["T_process"]
        print(f"  {k:5} {L['T_process']:9.0f}C {L['T_survive']:9.0f}C  {win:7.0f}K  {L['conf']:5}  {L['name']}")
    print("\n  (T_process for E,EM is the LIVE champion anneal/dep temp; L,PM,M from literature.)")

    # --- pairwise conflicts ---
    conflicts = conflict_matrix()
    _hdr("PAIRWISE CONFLICTS  ('A below B' destroys A:  T_process(B) > T_survive(A))")
    if not conflicts:
        print("  none — any order is thermally feasible.")
    else:
        for (a, b), d in sorted(conflicts.items(), key=lambda kv: -kv[1]):
            print(f"  {a:3} CANNOT be below {b:3}   ({b} needs {LAYERS[b]['T_process']:.0f}C, "
                  f"{a} survives {LAYERS[a]['T_survive']:.0f}C  ->  {d:+.0f}K over)")
    # derived must-be-after partial order
    print("\n  => forced precedence (X must be built BEFORE Y, i.e. X below Y):")
    forced = {}
    for (a, b) in conflicts:
        # a-before-b is infeasible -> b must be before a
        forced.setdefault(b, set()).add(a)
    for y in keys:
        if forced.get(y):
            print(f"     {', '.join(sorted(forced[y])):20} before {y}")

    # --- enumerate all build orders ---
    all_orders = list(permutations(keys))
    feas_all = [o for o in all_orders if order_feasible(o)[0]]
    feas_arch = [o for o in feas_all if o[-1] == ARCH_LAST]

    _hdr("BUILD-ORDER SEARCH (5! = 120 orderings)")
    print(f"  thermally feasible orderings              : {len(feas_all):3d} / {len(all_orders)}")
    print(f"  ... also satisfying architecture (M last) : {len(feas_arch):3d} / {len(all_orders)}")

    _hdr("VIABLE FABRICATION SEQUENCES (bottom -> top)")
    if not feas_arch:
        print("  NONE — thermal budget + architecture are mutually unsatisfiable.")
    for o in feas_arch:
        ok, rows = order_feasible(o)
        tight = min((m for (_, ml, m) in rows if ml > 0), default=float("inf"))
        seq = "  ->  ".join(o)
        print(f"\n  {seq}        [tightest margin {tight:+.0f}K]")
        for lyr, ml, m in rows:
            if ml > 0:
                flag = "  <-- TIGHTEST" if m == tight else ""
                print(f"     build {lyr:3} ({LAYERS[lyr]['T_process']:.0f}C), then sees {ml:5.0f}C later "
                      f"-> margin {m:+5.0f}K{flag}")
            else:
                print(f"     build {lyr:3} ({LAYERS[lyr]['T_process']:.0f}C) LAST — no later thermal load")

    # --- binding constraint ---
    _hdr("BINDING CONSTRAINT")
    pm = LAYERS["PM"]
    print(f"  ABSOLUTE: PM (Sb2Se3) survives only {pm['T_survive']:.0f}C, so it must be built AFTER every")
    print(f"  layer hotter than that (E {E_ANNEAL:.0f}C, EM {EM_DEP:.0f}C, L 350C). PM is pinned near the top.")
    if feas_arch:
        # tightest margin across viable flows = the real integration risk
        worst = min(
            (min((m for (_, ml, m) in order_feasible(o)[1] if ml > 0), default=float("inf")), o)
            for o in feas_arch
        )
        m_val, o = worst
        # which step is tightest
        for lyr, ml, mar in order_feasible(o)[1]:
            if mar == m_val:
                print(f"  TIGHTEST HEADROOM: {lyr} (finished, survives {LAYERS[lyr]['T_survive']:.0f}C) must sit "
                      f"through a later {ml:.0f}C step -> only {m_val:+.0f}K of margin.")
                print(f"  -> the real co-integration risk is the {lyr} layer surviving that step; verify with an")
                print(f"     anneal-ladder before committing the flow.")
                break

    _hdr("HONESTY / LIMITS")
    print("  * T_survive are materials-physics estimates from cited literature, NOT in-house")
    print("    TGA / anneal-ladder data. Tags: firm (well-established), est (reasoned), soft (assumed).")
    print("  * Model = peak-process-temp only. Real budgets also care about TIME-at-temp (thermal")
    print("    dose), thermal expansion mismatch, and interdiffusion — none modelled here.")
    print("  * M and PM share a ~250C ceiling; both are forced to the cold top of the stack.")
    print("  * E,EM process temps track the live champions — re-running after a champion change")
    print("    (e.g. a lower-anneal E) can WIDEN the feasible-ordering set.")

    return {
        "layers": {k: {"T_process": LAYERS[k]["T_process"], "T_survive": LAYERS[k]["T_survive"],
                       "conf": LAYERS[k]["conf"]} for k in keys},
        "conflicts": {f"{a}<{b}": d for (a, b), d in conflicts.items()},
        "feasible_thermal": [list(o) for o in feas_all],
        "feasible_with_arch": [list(o) for o in feas_arch],
    }


def main():
    ap = argparse.ArgumentParser(description="Morphium thermal-budget co-integration feasibility")
    ap.add_argument("--root", default=".", help="repo root (accepted for tool-suite consistency; unused)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()
    if args.json:
        # suppress the human report, just compute
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = analyse()
        print(json.dumps(res, indent=2))
    else:
        analyse()


if __name__ == "__main__":
    main()
