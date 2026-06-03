#!/usr/bin/env python3
"""
Cross-layer RELIABILITY view.
=============================
Two distinct reliability axes, both surfaced per layer:

  - fab-failure  : will it be MADE correctly?  (= 1 - model-aware MC yield)
  - endurance    : how many operating cycles will it LAST?  (cycle_life /
                   *_endurance from each layer's physics model)

A stack lasts only as long as its weakest layer (min endurance) and is made
correctly only if every layer is (compounded fab-survival). Champions are found
by the same robust+model-risk search as elsewhere (commit=False, ledger clean).

Endurance trust per layer (honest; literature-anchored 2026-06-03, see
docs/DATA_PROVENANCE.md for citations and caveats):
  E  endurance_cycles      — calibrated (HZO P-E cycling literature)
  PM cycling_endurance     — lit-grounded; GEOMETRY-driven (nanostructuring 1e8)
  L  operational_endurance — lit, but METRIC CAVEAT: a-IGZO switching is
                             effectively unbounded; real limit is Vth-drift
                             LIFETIME (time), not cycles
  EM actuation_endurance   — lit-grounded: sub-coercive piezo is ~fatigue-free
                             (>=1e12); ferroelectric switching would be ~1e8
  M  cycle_life            — lit-grounded (MEMS charging/contact data); the
                             foglet-specific magnitudes are still extrapolated

Usage:
  python3 tools/reliability.py --root . --model-risk
"""
import sys
import os
import argparse
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.morphium_kernel.kernel import KernelClient
from sensitivity_analysis import run_monte_carlo
from loop_kernel_adapter import run_search

ENDURANCE_KEY = {
    "E":  ("endurance_cycles",      "calibrated"),
    "PM": ("cycling_endurance",     "lit-grounded"),
    "L":  ("operational_endurance", "lit*(metric)"),   # *switching unbounded; real limit is Vth-drift LIFETIME
    "EM": ("actuation_endurance",   "lit-grounded"),   # sub-coercive piezo: fatigue-free
    "M":  ("cycle_life",            "lit-grounded"),   # MEMS charging/contact data; foglet magnitudes extrapolated
}
LABEL = {"E": "E  (HZO ferro)", "EM": "EM (ScAlN piezo)", "PM": "PM (Sb2Se3 photon)",
         "L": "L  (IGZO TFT)", "M": "M  (foglet mech)"}


def main():
    ap = argparse.ArgumentParser(description="Morphium cross-layer reliability view")
    ap.add_argument("--root", default=".")
    ap.add_argument("--model-risk", action="store_true", dest="model_risk")
    ap.add_argument("--mc", type=int, default=2000)
    ap.add_argument("--search-budget", type=int, default=120, dest="search_budget")
    ap.add_argument("--search-mc", type=int, default=48, dest="search_mc")
    args = ap.parse_args()
    random.seed(7)

    kc = KernelClient(project_root=args.root)
    ms = 1.0 if args.model_risk else 0.0
    ytag = "process+model" if args.model_risk else "process-only"
    print(f"Reliability board (fab-failure axis = {ytag}); finding champions "
          f"(live robust search, budget={args.search_budget})...\n", flush=True)

    rows = []     # (layer, fab_failure_pct, endurance_cycles)
    mstack = {}
    for layer in ("E", "EM", "PM", "L"):
        c = run_search(layer, args.search_budget, kc, robust=True, model_risk=True,
                       mc_samples=args.search_mc, quiet=True, commit=False)
        st = c["state"]
        y, _ = run_monte_carlo(kc, layer, st, n_samples=args.mc, model_sigma_scale=ms)
        r = kc.simulate(layer, st, seed=42)
        m = r.get("metrics", r.get("data", {}))
        endur = m.get(ENDURANCE_KEY[layer][0], 0)
        rows.append((layer, (1.0 - y) * 100.0, endur))
        if layer == "EM":
            mstack["EM_d33_pC_N"] = m.get("d33_pC_N", 20.0)
        elif layer == "E":
            mstack["E_endurance_cycles"] = m.get("endurance_cycles", 1e10)
        elif layer == "PM":
            mstack["PM_loss_k"] = m.get("loss_k", 1e-5)

    # M foglet — searched too (its design trades field vs failure/endurance)
    cM = run_search("M", args.search_budget, kc, robust=True, model_risk=True,
                    mc_samples=args.search_mc, quiet=True, commit=False)
    stM = cM["state"]
    stM["stack"] = mstack
    yM, _ = run_monte_carlo(kc, "M", stM, n_samples=args.mc, model_sigma_scale=ms)
    mM = kc.simulate("M", stM, seed=42)["metrics"]
    rows.append(("M", (1.0 - yM) * 100.0, mM.get("cycle_life", 0)))

    print(f"  {'layer':18} {'fab-failure':>12} {'endurance (cyc)':>18}  {'endurance trust':>15}")
    print(f"  {'-'*65}")
    for layer, fab, endur in rows:
        print(f"  {LABEL[layer]:18} {fab:10.2f}%  {endur:16.2e}    {ENDURANCE_KEY[layer][1]:>15}")

    valid = [e for _, _, e in rows if e > 0]
    stack_endur = min(valid) if valid else 0
    weak_e = min(rows, key=lambda r: (r[2] if r[2] > 0 else float('inf')))[0]
    surv = 1.0
    for _, fab, _ in rows:
        surv *= (1.0 - fab / 100.0)
    weak_f = max(rows, key=lambda r: r[1])[0]
    print(f"  {'-'*65}")
    print(f"\n  Stack operational endurance = {stack_endur:.2e} cycles "
          f"(limited by {weak_e} — its life caps the system's)")
    print(f"  Stack fab-survival          = {surv*100:.1f}%  "
          f"(all layers made correctly; weakest = {weak_f})")
    print(f"  M-foglet failure_rate       = {mM.get('failure_rate_pct')}%  "
          f"(model's own combined-margin metric)")
    print(f"\n  Note: endurance values are literature-anchored (2026-06-03) but carry"
          f"\n  caveats — L's metric is ill-defined (a-IGZO switching is effectively"
          f"\n  unbounded; real limit is Vth-drift LIFETIME), and M's foglet-specific"
          f"\n  magnitudes are extrapolated. Treat as order-of-magnitude; see"
          f"\n  docs/DATA_PROVENANCE.md for the trust + citations behind each.")


if __name__ == "__main__":
    main()
