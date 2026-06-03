#!/usr/bin/env python3
"""
Morphium-M composite stack-yield model.
========================================
M (foglets) is the only COMPOSITE layer: its contract declares a hard
dependency on E/EM/PM (`required_layers: [E, EM, PM]`), but the M simulator
models foglet mechanics standalone and ignores the stack beneath it. This tool
implements the composite the contract always intended:

    P(M-stack works) = P(M foglet ok) x P(E ok) x P(EM ok) x P(PM ok)

- The E/EM/PM terms are the model-aware (process+model) Monte-Carlo yields of
  their champions, reusing run_monte_carlo from sensitivity_analysis.
- The M-foglet term is an MC over the foglet's own fab-sensitive knobs
  (electrode gap, drive voltage, area), gated by a minimum latch force AND a
  dielectric-breakdown guard (field = V/gap must stay under the HfO2 limit).

A foglet can only function if the materials under it are fabricated correctly,
so the stack yield is bounded by the WEAKEST sub-layer. This surfaces where to
invest: improving the bottleneck layer lifts the whole system.

First-pass caveats (documented, like the other calibrations):
- Sub-layers assumed independent (no cross-layer fab correlation). Real
  correlated process steps would change the product; independence is the
  honest first pass and an UPPER bound if failures are positively correlated.
- M is absent from phi.json, so its model uncertainty is the uncalibrated
  default (40%) under --model-risk. M sigma/thresholds below are first-pass.

Usage:
  python3 tools/stack_yield.py --root .                # process-only
  python3 tools/stack_yield.py --root . --model-risk   # + simulator trust
"""
import sys
import os
import argparse
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.morphium_kernel.kernel import KernelClient
from sensitivity_analysis import run_monte_carlo, model_uncertainty_for
from loop_kernel_adapter import run_search


def _recipe(layer, state):
    """Compact champion recipe for display."""
    if layer == "L":
        comp = state["materials"]["channel_composition"]
        cats = {k: v for k, v in comp.items() if k != "O"}
        t = sum(cats.values()) or 1.0
        return "cation " + " ".join(f"{k}={v/t:.2f}" for k, v in cats.items())
    return str(state.get("formula", ""))

# Canonical M foglet champion (HfO2:DLC shell) — from layers/M/api.py example.
M_CHAMPION = {
    "foglet": {
        "structure": {"shell_material": "HfO2:DLC"},
        "latching": {"type": "electrostatic",
                     "electrode_geometry": {"area_um2": 100.0, "gap_nm": 50.0}},
        "adhesion": {"type": "dry_gecko", "pad_area_um2": 200.0},
        "power": {"max_voltage_V": 40.0},
    },
}

# Foglet fab process sigma (relative). Latch force F ∝ V^2 / gap^2, so the
# electrode GAP is the dominant fab risk; drive voltage is supply-regulated
# (tight); electrode area is lithography-limited.
M_SIGMA = {"gap_nm": 0.08, "max_voltage_V": 0.02, "area_um2": 0.03}

# Foglet promotion thresholds:
#  - latch force must clear a useful-hold floor. A ~100 µm foglet weighs ~1e-5 mN;
#    a meaningful latch must also resist locomotion shear and carry payload
#    (~100x self-weight), i.e. ~1e-2 mN, with margin. Floor set to 0.1 mN.
#    (Was 1.0 mN — un-justified, and only cleared by the audit-C-1 25x-inflated
#    force; with the corrected air-gap physics the champion is ~0.28 mN.)
#  - electrode field V/gap must stay below the HfO2 dielectric-breakdown limit
#    (thin ALD HfO2 ~10 MV/cm = 1.0 V/nm; conservative-ish upper guard).
M_MIN_LATCH_mN = 0.1
M_BREAKDOWN_V_PER_NM = 1.0


def foglet_yield(kc, champ, n=2000, model_scale=0.0, stack=None):
    """MC over the foglet's fab-sensitive knobs. Returns (yield, fail_counts).
    `stack` carries the E/EM/PM champion metrics the M model couples to."""
    unc, _ = model_uncertainty_for(kc, "M")  # M absent from phi -> uncalibrated default
    stack = stack or {}
    passed = 0
    fail = {"latch_force": 0, "dielectric_breakdown": 0}
    f = champ["foglet"]
    gap0 = f["latching"]["electrode_geometry"]["gap_nm"]
    v0 = f["power"]["max_voltage_V"]
    area0 = f["latching"]["electrode_geometry"]["area_um2"]
    for t in range(n):
        seed = 5000 + t
        gap = max(gap0 * (1 + random.gauss(0, M_SIGMA["gap_nm"])), 1.0)
        volt = max(v0 * (1 + random.gauss(0, M_SIGMA["max_voltage_V"])), 0.1)
        area = max(area0 * (1 + random.gauss(0, M_SIGMA["area_um2"])), 1.0)
        st = {"foglet": {**f,
                         "latching": {**f["latching"],
                                      "electrode_geometry": {"area_um2": area, "gap_nm": gap}},
                         "power": {**f["power"], "max_voltage_V": volt}},
              "stack": stack,
              "seed": seed}
        r = kc.simulate("M", st, seed=seed)
        force = r.get("metrics", {}).get("latch_normal_force_mN", 0.0)
        if model_scale > 0:
            force *= (1 + random.gauss(0, unc * model_scale))
        field = volt / gap  # V/nm
        ok = True
        if field > M_BREAKDOWN_V_PER_NM:
            fail["dielectric_breakdown"] += 1
            ok = False
        if force < M_MIN_LATCH_mN:
            fail["latch_force"] += 1
            ok = False
        if ok:
            passed += 1
    return passed / n, fail


def main():
    ap = argparse.ArgumentParser(description="Morphium-M composite stack-yield model")
    ap.add_argument("--root", default=".")
    ap.add_argument("--model-risk", action="store_true", dest="model_risk",
                    help="Fold per-layer simulator uncertainty (phi.json) into every yield.")
    ap.add_argument("--mc", type=int, default=2000, help="MC samples per layer (default 2000)")
    ap.add_argument("--search-budget", type=int, default=120, dest="search_budget",
                    help="GA budget for finding each sub-layer's current champion (default 120)")
    ap.add_argument("--search-mc", type=int, default=48, dest="search_mc",
                    help="MC samples/candidate during champion search (default 48)")
    args = ap.parse_args()
    random.seed(7)

    kc = KernelClient(project_root=args.root)
    ms = 1.0 if args.model_risk else 0.0
    ytag = "process+model" if args.model_risk else "process-only"

    # Find each sub-layer's CURRENT champion via a live robust+model-risk search
    # (commit=False so the ledger stays clean), then evaluate its yield in the
    # requested mode. This reflects the engine's current calibration/constraints
    # rather than a stale stored dict.
    print("Finding current robust+calibrated champions (live search, "
          f"budget={args.search_budget})...", flush=True)
    subs, recipes = {}, {}
    mstack = {}   # E/EM/PM champion metrics the M foglet model couples to
    for layer in ("E", "EM", "PM"):
        champ = run_search(layer, args.search_budget, kc, robust=True, model_risk=True,
                           mc_samples=args.search_mc, quiet=True, commit=False)
        state = champ["state"]
        y, _ = run_monte_carlo(kc, layer, state, n_samples=args.mc, model_sigma_scale=ms)
        subs[layer] = y
        recipes[layer] = _recipe(layer, state)
        # Pull the metrics the M model depends on (EM->actuation, E->controller,
        # PM->comms) so the foglet is a genuine composite of THIS run's champions.
        r = kc.simulate(layer, state, seed=42)
        cm = r.get("metrics", r.get("data", {}))
        if layer == "EM":
            mstack["EM_d33_pC_N"] = cm.get("d33_pC_N", 20.0)
        elif layer == "E":
            mstack["E_endurance_cycles"] = cm.get("endurance_cycles", 1e10)
        elif layer == "PM":
            mstack["PM_loss_k"] = cm.get("loss_k", 1e-5)

    fog, fog_fail = foglet_yield(kc, M_CHAMPION, n=args.mc, model_scale=ms, stack=mstack)

    stack = fog
    for y in subs.values():
        stack *= y

    # Bottleneck = weakest contributor (incl. the foglet term).
    contrib = dict(subs)
    contrib["M-foglet"] = fog
    bottleneck = min(contrib, key=contrib.get)

    f = M_CHAMPION["foglet"]
    field0 = f["power"]["max_voltage_V"] / f["latching"]["electrode_geometry"]["gap_nm"]

    print(f"\n{'='*64}")
    print(f"  MORPHIUM-M COMPOSITE STACK YIELD   (yield axis = {ytag})")
    print(f"  {args.mc} MC samples/layer; sub-layers assumed independent")
    print(f"{'='*64}")
    print(f"  Sub-layer champions: CURRENT robust+calibrated (live search).\n")
    print(f"  Stack = M-foglet x E x EM x PM  (M requires E/EM/PM per contract)\n")
    print(f"    {'E   (HZO ferro)':<22} {subs['E']*100:6.1f}%   {recipes['E']}")
    print(f"    {'EM  (ScAlN piezo)':<22} {subs['EM']*100:6.1f}%   {recipes['EM']}")
    print(f"    {'PM  (Sb2Se3 photon)':<22} {subs['PM']*100:6.1f}%   {recipes['PM']}")
    print(f"    {'M-foglet (mechanics)':<22} {fog*100:6.1f}%   "
          f"[field {field0:.2f} V/nm vs {M_BREAKDOWN_V_PER_NM:.2f} guard; "
          f"fails {fog_fail}]")
    print(f"  {'-'*40}")
    print(f"    {'STACK (composite)':<22} {stack*100:6.1f}%")
    print(f"\n  Bottleneck: {bottleneck} ({contrib[bottleneck]*100:.1f}%) — "
          f"lifting it raises the whole stack most.")
    print(f"  Note: stack <= weakest layer; M's own mechanics are "
          f"{'NOT ' if fog >= min(subs.values()) else ''}the limiter here.")


if __name__ == "__main__":
    main()
