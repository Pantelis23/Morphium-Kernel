#!/usr/bin/env python3
"""
Morphium SINGLE-LAYER TEST-CHIP SPECS — the falsifiable bridge to silicon.
==========================================================================
Step 1 of the watch path (docs/STATE_OF_MORPHIUM.md): turn each calibrated
champion into ONE standalone test chip that the simulation COMMITS TO PREDICTING.
For each layer this emits:
  * the exact champion recipe to fabricate,
  * the process window (deposition/anneal temp, from integration.py),
  * the metric(s) the kernel PREDICTS, each with a +/- uncertainty band taken
    straight from config/phi.json (_uncertainty_pct),
  * the metrology method + instrument that measures it,
  * the FALSIFICATION criterion: if the measured value lands outside the band,
    the model is wrong for that metric — full stop.

This is what makes Morphium falsifiable: the sim stakes a number + a band on each
layer BEFORE fabrication, so first silicon confirms or refutes a specific claim.
The four lit-calibrated layers (E/L/EM/PM) are first-class; M is a heuristic
composite (not literature-calibrated) and is flagged as lower-confidence.

HONESTY: predicted values are simulation outputs; bands are the calibration
uncertainty, NOT a guarantee of physical correctness. See docs/DATA_PROVENANCE.md.

Usage:  python3 tools/testchip.py            # all layers
        python3 tools/testchip.py --layer E  # one layer
        python3 tools/testchip.py --json
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.morphium_kernel.kernel import KernelClient
from sensitivity_analysis import extract_metrics, CHAMPIONS
from integration import LAYERS as INTEG  # live per-layer process temps

PHI = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "phi.json")))

# Per-layer: which predicted metrics to stake, their unit, the process/stack, the
# metrology method, and a confidence tag. Metric keys must match extract_metrics().
SPECS = {
    "E": {
        "name": "HfZrO2 ferroelectric capacitor (1T1C / FeCAP test array)",
        "recipe": lambda c: f"{c.get('formula','Hf0.5Zr0.5O2')}, {c.get('thickness_nm',10)} nm, {c.get('electrode','TiN')} electrodes",
        "process": "ALD HfZrO2; RTA crystallisation anneal; TiN/Ru top+bottom electrodes",
        "metrics": [("polarization_uC_cm2", "uC/cm2", "2Pr (remanent polarization x2)"),
                    ("dielectric_constant_k", "", "small-signal permittivity"),
                    ("endurance_cycles", "cycles", "cycles-to-50%-2Pr-loss")],
        "metrology": ("P-E hysteresis loop + C-V + endurance cycling",
                      "Radiant Precision / aixACCT TF-2000 ferroelectric analyzer",
                      "2Pr from saturated P-E loop; k from C-V at small signal; endurance from 2Pr vs cycle count"),
        "conf": "calibrated",
    },
    "L": {
        "name": "IGZO bottom-gate TFT (W/L array)",
        "recipe": lambda c: "IGZO channel, cation " + ", ".join(
            f"{k} {v:.3f}" for k, v in c.get("materials", {}).get("channel_composition", {}).items()),
        "process": "Sputter/PLD IGZO ~30 nm on Al2O3/ALD dielectric, glass substrate; ~350 C BEOL anneal; Al2O3 passivation",
        "metrics": [("mobility_cm2_Vs", "cm2/Vs", "saturation field-effect mobility"),
                    ("SS_mV_dec", "mV/dec", "subthreshold swing")],
        "metrology": ("DC Id-Vg/Id-Vd + Hall, then PBS bias-stress",
                      "Keithley 4200-SCS parameter analyzer (+ Hall bar)",
                      "mu_sat from sqrt(Id)-Vg slope; SS from log(Id)-Vg; on/off from Id range; dVth from PBS"),
        "conf": "calibrated",
    },
    "EM": {
        "name": "ScAlN piezo capacitor / cantilever (d33 coupon)",
        "recipe": lambda c: f"{c.get('formula','Sc0.4Al0.6N')} on {c.get('substrate','Si')}",
        "process": "Reactive pulsed-DC magnetron co-sputter ScAlN on Mo/Si; dep ~490 C; Mo top electrode",
        "metrics": [("d33_pC_N", "pC/N", "longitudinal piezo coefficient")],
        "metrology": ("Berlincourt d33 meter + PFM + laser-Doppler vibrometry",
                      "Berlincourt PiezoMeter (PM300) / PFM (Bruker) / Polytec LDV",
                      "d33 from charge-per-force (Berlincourt) and displacement-per-volt (LDV); cross-check with PFM"),
        "conf": "calibrated (champion d33 reads conservative ~21; lit plateau ~24-27, see phi residual)",
    },
    "PM": {
        "name": "Sb2Se3 phase-change film (ellipsometry coupon + waveguide)",
        "recipe": lambda c: f"{c.get('formula','Sb2:Se3:Ge:Cl')} (amorphous as-dep, then crystallised)",
        "process": "Sputter/evaporate Sb2Se3:Ge:Cl ~30-200 nm; crystallise ~200 C; measure both phases",
        "metrics": [("delta_n", "", "n_cryst - n_amorph @1550nm"),
                    ("loss_k", "", "extinction coefficient @1550nm")],
        "metrology": ("Spectroscopic ellipsometry (amorphous vs crystallised) + cut-back waveguide loss",
                      "J.A. Woollam M-2000 ellipsometer @1550nm; cut-back on integrated waveguides",
                      "delta_n from n_c - n_a; k from extinction; device loss (dB/cm) from cut-back"),
        "conf": "calibrated (champion delta_n ~0.785 is calibration-dominated; pure-Sb2Se3 anchor 0.765 is the firm number)",
    },
    "M": {
        "name": "Foglet latch / adhesion coupon (macro-scale proxy first)",
        "recipe": lambda c: "HfO2:DLC composite foglet (depends on E/EM/PM beneath)",
        "process": "Macro parallel-plate cap (1 cm2, defined gap) for latch; shell-vs-glass shear for adhesion",
        "metrics": [],  # M outputs are composite/heuristic; specify proxies in prose
        "metrology": ("Force-V profiling (load cell + HV) + shear pull test",
                      "Instron + Keithley 2410 HV; shear rig",
                      "k_el = F/V^2 from latch sweep; shear strength (kPa) from pull test"),
        "conf": "HEURISTIC (not literature-calibrated) — validate the component physics, not a champion number",
    },
}

LAYER_ORDER = ["E", "L", "EM", "PM", "M"]


def _hdr(title):
    print(f"\n{'='*74}\n  {title}\n{'='*74}")


def champion_metrics(kc, layer):
    st = {k: v for k, v in CHAMPIONS[layer].items() if k != "seed"}
    res = kc.simulate(layer, st, seed=CHAMPIONS[layer].get("seed", 42))
    return extract_metrics(layer, res)


def build(layer, kc):
    spec = SPECS[layer]
    champ = CHAMPIONS.get(layer, {})  # M is a composite -> no standalone champion
    unc = float(PHI.get(layer, {}).get("_uncertainty_pct", 0.0)) / 100.0
    proc_T = INTEG.get(layer, {}).get("T_process")
    m = champion_metrics(kc, layer) if spec["metrics"] else {}
    preds = []
    for key, unit, desc in spec["metrics"]:
        v = m.get(key)
        if v is None:
            continue
        lo, hi = v * (1.0 - unc), v * (1.0 + unc)
        preds.append({"metric": key, "desc": desc, "unit": unit, "value": v,
                      "band_lo": lo, "band_hi": hi, "unc_pct": unc * 100.0})
    return {
        "layer": layer, "name": spec["name"], "conf": spec["conf"],
        "recipe": spec["recipe"](champ), "process": spec["process"], "process_T_C": proc_T,
        "metrology": {"method": spec["metrology"][0], "instrument": spec["metrology"][1],
                      "extract": spec["metrology"][2]},
        "predictions": preds,
    }


def _fmt(v):
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1e4 or a < 1e-2:
        return f"{v:.2e}"
    return f"{v:.3g}"


def report(layers):
    kc = KernelClient(project_root=".")
    out = []
    for layer in layers:
        b = build(layer, kc)
        out.append(b)
        _hdr(f"TEST CHIP — Layer {layer}: {b['name']}")
        print(f"  confidence   : {b['conf']}")
        print(f"  champion     : {b['recipe']}")
        tC = f"{b['process_T_C']:.0f} C" if b['process_T_C'] is not None else "n/a"
        print(f"  process      : {b['process']}")
        print(f"               : peak process temp ~{tC} (co-integration order: see integration.py)")
        print(f"  metrology    : {b['metrology']['method']}")
        print(f"               : {b['metrology']['instrument']}")
        print(f"               : extract -> {b['metrology']['extract']}")
        if b["predictions"]:
            print(f"  PREDICTIONS the sim stakes (measured must land in the band, else model FALSIFIED):")
            for p in b["predictions"]:
                u = f"{p['unit']}" if p["unit"] else ""
                print(f"     {p['metric']:22} = {_fmt(p['value']):>10} {u:7}  band [{_fmt(p['band_lo'])} .. {_fmt(p['band_hi'])}] (+-{p['unc_pct']:.0f}%)  -- {p['desc']}")
        else:
            print(f"  PREDICTIONS  : (heuristic layer — validate component physics, no staked champion number)")

    _hdr("HOW TO USE THIS")
    print("  Each chip is a FALSIFICATION test. Fabricate the champion recipe, measure with the")
    print("  stated instrument, and check each metric against its band:")
    print("    * inside  the band  -> the calibrated model is confirmed for that metric.")
    print("    * outside the band  -> the model is wrong there; feed the measurement back as a new")
    print("      phi anchor (config/phi.json) and re-derive. The band IS the falsifiable claim.")
    print("  Build order is independent: E, L, EM, PM coupons can be fabricated in parallel; none")
    print("  needs the full stack. Run E/L first (highest confidence + watch-critical).")
    print("  NOTE: docs METROLOGY_PLAN.md / FABRICATION_PLAN.md (v1.0) predate calibration — this")
    print("  tool is the live source of truth for predicted numbers.")
    return out


def main():
    ap = argparse.ArgumentParser(description="Morphium single-layer test-chip specs")
    ap.add_argument("--layer", choices=LAYER_ORDER, help="one layer only")
    ap.add_argument("--root", default=".", help="repo root (tool-suite consistency)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON")
    args = ap.parse_args()
    layers = [args.layer] if args.layer else LAYER_ORDER
    if args.json:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = report(layers)
        print(json.dumps(out, indent=2, default=float))
    else:
        report(layers)


if __name__ == "__main__":
    main()
