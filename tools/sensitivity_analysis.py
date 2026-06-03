"""
Morphium Sensitivity Analysis & Monte Carlo Yield Prediction
============================================================
Pre-lab computational tool to:

  1. Numerical Jacobian  — ∂metric/∂xi for each composition variable
     Shows which variables have the most leverage on each metric.

  2. Monte Carlo Yield   — 10,000 samples with Gaussian process noise
     Predicts what fraction of fabricated devices will pass spec given
     realistic composition variability (e.g. ±2% from sputtering target
     inhomogeneity, ±5% from run-to-run O₂ flow variation).

  3. Pareto Front Mapper — multi-objective trade-off curves
     For Layer L:  mobility vs crystallization_risk, mobility vs Ioff
     For Layer PM: Δn vs k  (FOM = Δn/k)
     For Layer E:  polarization vs endurance, polarization vs k
     For Layer EM: d33 vs sec_phase_risk vs Sc fraction

  4. Process Control Spec — which variables must be held tightest

Usage:
  python3 tools/sensitivity_analysis.py --layer L
  python3 tools/sensitivity_analysis.py --layer PM
  python3 tools/sensitivity_analysis.py --layer E
  python3 tools/sensitivity_analysis.py --layer EM
  python3 tools/sensitivity_analysis.py --all
  python3 tools/sensitivity_analysis.py --layer L --mc-samples 10000
  python3 tools/sensitivity_analysis.py --layer L --pareto
"""

import sys
import os
import json
import math
import argparse
import random

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.morphium_kernel.kernel import KernelClient


# ---------------------------------------------------------------------------
# Champion states (best known compositions for each layer)
# ---------------------------------------------------------------------------

CHAMPIONS = {
    "L": {
        # Regenerated 2026-06-03 (audit M-1): the prior champion had cation
        # Zn=0.003 (effectively In-Ga-O), violating the literature-justified
        # Zn>=0.10 floor. This one satisfies it: cation In=0.628/Ga=0.272/Zn=0.100,
        # mobility ~20 cm2/Vs (robust+model-risk search under the current floors).
        "materials": {
            "channel_material": "IGZO",
            "channel_composition": {
                "In": 0.2522,
                "Ga": 0.1093,
                "Zn": 0.0402,
                "O": 0.5983
            }
        },
        "seed": 42
    },
    "PM": {
        "formula": "Sb2:Se3:Ge:Cl",
        "seed": 42
    },
    "E": {
        "formula": "Hf0.4Zr0.557Al0.043O2",
        "thickness_nm": 11.7,
        "anneal_temp_C": 559.0,
        "seed": 42
    },
    "EM": {
        "formula": "Sc0.38Al0.62N",
        "substrate": "Si",
        "dep_temp_C": 490.0,
        "seed": 42
    },
}

# What fraction of each variable represents a realistic process sigma
# (± 1 sigma from target due to deposition variability)
PROCESS_SIGMA = {
    "L": {
        "In": 0.025,   # ±2.5% absolute from sputtering inhomogeneity
        "Ga": 0.020,
        "Zn": 0.001,   # ±0.1% absolute — champion has Zn=0.001; σ=0.010 would be 10× the value
        "O":  0.030,   # ±3% absolute — O₂ flow most variable
    },
    "PM": {
        "Sb": 0.03,
        "Se": 0.03,
        "Ge": 0.005,
        "Cl": 0.002,
    },
    "E": {
        "x_Zr":        0.020,   # ±2% Zr fraction (dual-target co-sputter)
        "thickness_nm": 0.5,    # ±0.5 nm ALD cycle control
        "anneal_temp_C": 10.0,  # ±10°C furnace uniformity
    },
    "EM": {
        "x_Sc":      0.010,   # ±1% absolute Sc target control (sputtering)
        "dep_temp_C": 15.0,   # ±15°C substrate heater uniformity
    },
    "M": {   # RELATIVE fractions (foglet knobs span orders of magnitude)
        "area_um2":      0.03,
        "gap_nm":        0.08,   # litho/deposition — dominates latch & breakdown
        "max_voltage_V": 0.02,
        "pad_area_um2":  0.05,
    },
}

# Promotion thresholds (pass/fail for Monte Carlo yield)
PROMOTION_THRESHOLDS = {
    "L": {
        "mobility_cm2_Vs": ("ge", 10.0),
        "Ioff_A":          ("le", 1e-9),
        "SS_mV_dec":       ("le", 300.0),
        "crystallization_risk": ("le", 0.5),
    },
    "PM": {
        "fom":     ("ge", 500.0),
        "delta_n": ("ge", 0.30),
        "loss_k":  ("le", 1e-4),
    },
    "E": {
        "polarization_uC_cm2": ("ge", 10.0),
        "dielectric_constant_k": ("ge", 15.0),
        "endurance_cycles": ("ge", 1e9),
    },
    "EM": {
        "d33_pC_N":        ("ge", 10.0),
        "_sec_phase_risk": ("le", 0.60),   # sec_risk > 0.60 → secondary ScN/Sc2O3 very likely
    },
    "M": {
        "failure_rate_pct":      ("le", 5.0),    # foglet should fail <5% of the time
        "latch_normal_force_mN": ("ge", 0.1),    # useful-hold floor (>> ug-foglet weight)
        "payload_ratio":         ("ge", 10.0),   # hold >=10x self-weight
        "max_speed_mm_s":        ("ge", 1.0),    # useful locomotion
        "cycle_life":            ("ge", 1e4),    # latch endurance
    },
}


# ---------------------------------------------------------------------------
# Model (epistemic) uncertainty — how much do we trust the SIMULATOR itself?
# ---------------------------------------------------------------------------
# PROCESS_SIGMA (above) answers "will it survive fab variation?". Model noise
# answers the orthogonal question "is the simulator even telling the truth?".
# Per-layer trust is hand-recorded in config/phi.json (_calibration_status,
# _uncertainty_pct). A recipe that looks 100% safe on an *uncalibrated* model
# is risk-UNKNOWN, not risk-free — folding this in stops the search from
# trusting sim regions that were never checked against reality.

# Assumed relative metric uncertainty for layers phi.json marks "uncalibrated"
# (no sim-to-real anchor at all). Deliberately large: we genuinely don't know.
UNCALIBRATED_MODEL_UNC = 0.40

_PHI_META_CACHE = {}

def model_uncertainty_for(kc, layer):
    """Return (relative_metric_uncertainty, calibration_status) for a layer.

    Reads config/phi.json trust metadata. Calibrated layers use their recorded
    _uncertainty_pct; uncalibrated/absent layers fall back to the deliberately
    large UNCALIBRATED_MODEL_UNC (we genuinely don't know how wrong the sim is).
    """
    root = str(getattr(kc, "root", "."))
    if root not in _PHI_META_CACHE:
        try:
            with open(os.path.join(root, "config", "phi.json")) as f:
                _PHI_META_CACHE[root] = json.load(f)
        except Exception:
            _PHI_META_CACHE[root] = {}
    meta = _PHI_META_CACHE[root].get(layer, {})
    status = meta.get("_calibration_status", "absent")
    unc_pct = meta.get("_uncertainty_pct")
    if unc_pct is not None:
        return float(unc_pct) / 100.0, status
    return UNCALIBRATED_MODEL_UNC, status


def extract_metrics(layer, result):
    """Flatten layer-specific result dict to a simple metric dict."""
    if layer == "L":
        m = result.get("metrics", result)
        return {k: v for k, v in m.items() if not k.startswith("_") and k != "seed"}
    elif layer == "PM":
        m = result.get("metrics", result)
        return {k: v for k, v in m.items() if not k.startswith("_") and k != "seed"}
    elif layer == "E":
        d = result.get("data", result)
        return {k: v for k, v in d.items()
                if not k.startswith("_")
                and k not in ("seed", "formula", "thickness_nm", "anneal_temp_C")}
    elif layer == "EM":
        m = result.get("metrics", result)
        # Keep _sec_phase_risk (used as MC threshold) but drop other internal keys
        return {k: v for k, v in m.items()
                if (not k.startswith("_") or k == "_sec_phase_risk") and k != "seed"}
    elif layer == "M":
        m = result.get("metrics", result)
        return {k: v for k, v in m.items() if not k.startswith("_") and k != "seed"}
    return result


def passes_thresholds(layer, metrics):
    """Returns True if all metrics meet the promotion threshold."""
    thresholds = PROMOTION_THRESHOLDS.get(layer, {})
    for metric, (op, val) in thresholds.items():
        m_val = metrics.get(metric)
        if m_val is None:
            return False
        try:
            m_val = float(m_val)
        except (ValueError, TypeError):
            return False
        if op == "ge" and m_val < val:
            return False
        if op == "le" and m_val > val:
            return False
    return True


# ---------------------------------------------------------------------------
# 1. Numerical Jacobian
# ---------------------------------------------------------------------------

def compute_jacobian(kc, layer, state, h_frac=0.02):
    """
    Compute ∂metric/∂xi  for each perturbable variable via central differences.

    h_frac: step size as fraction of current value (or absolute if value ≤ 0).
    Returns dict: {variable: {metric: sensitivity}}
    """
    def run(s):
        r = kc.simulate(layer, s, seed=s.get("seed", 42))
        return extract_metrics(layer, r)

    base_metrics = run(state)

    jacobian = {}

    if layer == "L":
        comp = state["materials"]["channel_composition"]
        for el in list(comp.keys()):
            h = max(h_frac * comp[el], 1e-3) if comp[el] > 0 else h_frac
            # Forward
            s_fwd = json.loads(json.dumps(state))
            s_fwd["materials"]["channel_composition"][el] += h
            m_fwd = run(s_fwd)
            # Backward
            s_bck = json.loads(json.dumps(state))
            s_bck["materials"]["channel_composition"][el] -= h
            m_bck = run(s_bck)

            jacobian[el] = {}
            for metric in base_metrics:
                try:
                    jacobian[el][metric] = (float(m_fwd[metric]) - float(m_bck[metric])) / (2 * h)
                except (TypeError, ValueError, KeyError):
                    jacobian[el][metric] = 0.0

    elif layer == "PM":
        # For PM, perturb atomic fractions in the champion formula
        # Champion: Sb2Se3:Ge:Cl → parse to get base fracs
        formula = state.get("formula", "Sb2Se3:Ge:Cl")
        import re
        atoms = re.findall(r'([A-Z][a-z]*)(\d*\.?\d*)', formula)
        raw = {}
        for el, amt_str in atoms:
            if el:
                amt = float(amt_str) if amt_str else 1.0
                raw[el] = raw.get(el, 0.0) + amt

        for el in list(raw.keys()):
            h = max(h_frac * raw[el], 0.01)
            # Perturb by rebuilding formula string
            def make_formula(perturb_el, delta):
                new_raw = {k: v + (delta if k == perturb_el else 0) for k, v in raw.items()}
                return ":".join(
                    f"{e}{round(v, 4)}" if v != 1.0 else e
                    for e, v in new_raw.items()
                    if v > 0
                )
            s_fwd = {**state, "formula": make_formula(el, h)}
            s_bck = {**state, "formula": make_formula(el, -h)}
            m_fwd = run(s_fwd)
            m_bck = run(s_bck)

            jacobian[el] = {}
            for metric in base_metrics:
                try:
                    jacobian[el][metric] = (float(m_fwd[metric]) - float(m_bck[metric])) / (2 * h)
                except (TypeError, ValueError, KeyError):
                    jacobian[el][metric] = 0.0

    elif layer == "E":
        import re as _re
        _formula = state.get("formula", "Hf0.4Zr0.557O2")
        _m_zr = _re.search(r'Zr(\d*\.?\d+)', _formula)
        _base_zr_from_state = float(_m_zr.group(1)) if _m_zr else 0.557

        variables = {
            "x_Zr":         ("formula", None),       # handled specially
            "thickness_nm": ("thickness_nm", 11.7),
            "anneal_temp_C": ("anneal_temp_C", 559.0),
        }
        for var, (key, default) in variables.items():
            base_val = state.get(key, default) if key != "formula" else _base_zr_from_state
            h = max(h_frac * abs(base_val), 0.01) if base_val != 0 else h_frac

            if var == "x_Zr":
                # Perturb Zr fraction — evaluated off-peak (champion at 0.557, not 0.5)
                base_zr = _base_zr_from_state
                def make_hzo(zr):
                    hf = round(1.0 - zr, 3)
                    return f"Hf{hf}Zr{zr}O2"
                s_fwd = {**state, "formula": make_hzo(base_zr + h)}
                s_bck = {**state, "formula": make_hzo(max(base_zr - h, 0.01))}
            else:
                s_fwd = {**state, key: base_val + h}
                s_bck = {**state, key: max(base_val - h, 0.1)}

            m_fwd = run(s_fwd)
            m_bck = run(s_bck)

            jacobian[var] = {}
            for metric in base_metrics:
                try:
                    jacobian[var][metric] = (float(m_fwd[metric]) - float(m_bck[metric])) / (2 * h)
                except (TypeError, ValueError, KeyError):
                    jacobian[var][metric] = 0.0

    elif layer == "EM":
        import re
        formula = state.get("formula", "Sc0.40Al0.60N")
        m_sc = re.search(r'Sc(\d*\.?\d+)', formula)
        base_xsc = float(m_sc.group(1)) if m_sc else 0.40

        # Perturb x_Sc
        h_sc = max(h_frac * base_xsc, 0.01)
        def make_scaln(xsc):
            xal = round(1.0 - xsc, 3)
            return f"Sc{round(xsc, 3)}Al{xal}N"
        s_fwd = {**state, "formula": make_scaln(min(base_xsc + h_sc, 0.42))}
        s_bck = {**state, "formula": make_scaln(max(base_xsc - h_sc, 0.10))}
        m_fwd = run(s_fwd)
        m_bck = run(s_bck)
        jacobian["x_Sc"] = {}
        for metric in base_metrics:
            try:
                jacobian["x_Sc"][metric] = (float(m_fwd[metric]) - float(m_bck[metric])) / (2 * h_sc)
            except (TypeError, ValueError, KeyError):
                jacobian["x_Sc"][metric] = 0.0

        # Perturb dep_temp_C
        base_T = state.get("dep_temp_C", 473.0)
        h_T = 20.0
        s_fwd = {**state, "dep_temp_C": base_T + h_T}
        s_bck = {**state, "dep_temp_C": base_T - h_T}
        m_fwd = run(s_fwd)
        m_bck = run(s_bck)
        jacobian["dep_temp_C"] = {}
        for metric in base_metrics:
            try:
                jacobian["dep_temp_C"][metric] = (float(m_fwd[metric]) - float(m_bck[metric])) / (2 * h_T)
            except (TypeError, ValueError, KeyError):
                jacobian["dep_temp_C"][metric] = 0.0

    return base_metrics, jacobian


def print_jacobian(layer, base_metrics, jacobian):
    """Pretty-print the Jacobian table."""
    print(f"\n{'='*70}")
    print(f"  Jacobian Analysis — Layer {layer}")
    print(f"  (∂metric/∂variable, evaluated at champion)")
    print(f"{'='*70}")

    metrics_to_show = [k for k in base_metrics if isinstance(base_metrics[k], (int, float))]
    vars_list = sorted(jacobian.keys())

    # Column widths
    col_w = 12
    header = f"  {'Variable':10s}" + "".join(f"{m[:col_w]:>{col_w}}" for m in metrics_to_show)
    print(header)
    print("  " + "-" * (10 + col_w * len(metrics_to_show)))

    for var in vars_list:
        row = f"  {var:10s}"
        for metric in metrics_to_show:
            sens = jacobian[var].get(metric, 0.0)
            if abs(sens) > 1e3:
                cell = f"{sens:>+{col_w}.2e}"
            elif abs(sens) > 1e-3:
                cell = f"{sens:>+{col_w}.4f}"
            else:
                cell = f"{sens:>+{col_w}.2e}"
            row += cell
        print(row)

    print("\n  Champion metrics:")
    for k, v in base_metrics.items():
        if isinstance(v, (int, float)):
            print(f"    {k}: {v}")


# ---------------------------------------------------------------------------
# 2. Monte Carlo Yield Prediction
# ---------------------------------------------------------------------------

def run_monte_carlo(kc, layer, state, n_samples=1000, sigma_scale=1.0,
                    model_sigma_scale=0.0):
    """
    Sample n_samples perturbed states from a Gaussian around the champion.
    Returns (yield_fraction, failed_metrics_histogram).

    sigma_scale scales PROCESS noise (input-knob fab variation). When
    model_sigma_scale > 0, ALSO perturbs the simulated output metrics by the
    layer's MODEL (epistemic) uncertainty from phi.json — so a sample must
    survive both fab variation AND possible simulator error to count as a pass.
    model_sigma_scale=0 (default) reproduces the original process-only yield.
    """
    sigmas = PROCESS_SIGMA.get(layer, {})
    passed = 0
    fail_counts = {}

    # Resolve model (epistemic) uncertainty once. 0 → disabled (process-only).
    model_unc = 0.0
    if model_sigma_scale > 0.0:
        model_unc, _ = model_uncertainty_for(kc, layer)
        model_unc *= model_sigma_scale

    for trial in range(n_samples):
        seed = 1000 + trial   # deterministic per trial

        if layer == "L":
            comp = {el: v + random.gauss(0, sigmas.get(el, 0.02) * sigma_scale)
                    for el, v in state["materials"]["channel_composition"].items()}
            # Re-normalize (composition must sum to 1 within each sublattice)
            total = sum(max(v, 0.001) for v in comp.values())
            comp  = {el: max(v, 0.001) / total for el, v in comp.items()}
            s = {"materials": {"channel_composition": comp}, "seed": seed}

        elif layer == "PM":
            import re
            formula = state.get("formula", "Sb2Se3:Ge:Cl")
            atoms = re.findall(r'([A-Z][a-z]*)(\d*\.?\d*)', formula)
            raw = {}
            for el, amt_str in atoms:
                if el:
                    amt = float(amt_str) if amt_str else 1.0
                    raw[el] = raw.get(el, 0.0) + amt
            new_raw = {el: max(v + random.gauss(0, sigmas.get(el, 0.02) * sigma_scale), 1e-4)
                       for el, v in raw.items()}
            formula_str = ":".join(
                f"{e}{round(v, 4)}" if round(v, 4) != 1.0 else e
                for e, v in new_raw.items()
            )
            s = {"formula": formula_str, "seed": seed}

        elif layer == "E":
            import re
            formula = state.get("formula", "Hf0.5Zr0.5O2")
            m = re.search(r'Zr(\d*\.?\d+)', formula)
            x_Zr = float(m.group(1)) if m else 0.5
            x_Zr_new = min(max(x_Zr + random.gauss(0, sigmas.get("x_Zr", 0.02) * sigma_scale), 0.01), 0.99)
            x_Hf_new = round(1.0 - x_Zr_new, 3)
            new_formula = f"Hf{x_Hf_new}Zr{round(x_Zr_new, 3)}O2"
            t_new  = max(state.get("thickness_nm", 10.0) + random.gauss(0, sigmas.get("thickness_nm", 0.5) * sigma_scale), 1.0)
            T_new  = state.get("anneal_temp_C", 450.0) + random.gauss(0, sigmas.get("anneal_temp_C", 10.0) * sigma_scale)
            s = {"formula": new_formula, "thickness_nm": t_new, "anneal_temp_C": T_new, "seed": seed}

        elif layer == "EM":
            import re
            formula = state.get("formula", "Sc0.40Al0.60N")
            m_sc = re.search(r'Sc(\d*\.?\d+)', formula)
            x_Sc = float(m_sc.group(1)) if m_sc else 0.40
            x_Sc_new = min(max(x_Sc + random.gauss(0, sigmas.get("x_Sc", 0.01) * sigma_scale), 0.10), 0.42)
            x_Al_new = round(1.0 - x_Sc_new, 3)
            new_formula = f"Sc{round(x_Sc_new, 3)}Al{x_Al_new}N"
            T_new = state.get("dep_temp_C", 473.0) + random.gauss(0, sigmas.get("dep_temp_C", 15.0) * sigma_scale)
            s = {"formula": new_formula, "substrate": state.get("substrate", "Al2O3"),
                 "dep_temp_C": T_new, "seed": seed}

        elif layer == "M":
            # Foglet design: perturb electrode area/gap, drive voltage, pad area
            # (relative sigmas). Nested foglet state; stack metrics passed through.
            f = state["foglet"]
            eg = f["latching"]["electrode_geometry"]
            area = max(eg["area_um2"] * (1 + random.gauss(0, sigmas.get("area_um2", 0.03) * sigma_scale)), 1.0)
            gap  = max(eg["gap_nm"]   * (1 + random.gauss(0, sigmas.get("gap_nm", 0.08) * sigma_scale)), 1.0)
            volt = max(f["power"]["max_voltage_V"] * (1 + random.gauss(0, sigmas.get("max_voltage_V", 0.02) * sigma_scale)), 0.1)
            pad  = max(f["adhesion"]["pad_area_um2"] * (1 + random.gauss(0, sigmas.get("pad_area_um2", 0.05) * sigma_scale)), 1.0)
            s = {"foglet": {**f,
                            "latching": {**f["latching"],
                                         "electrode_geometry": {"area_um2": area, "gap_nm": gap}},
                            "power":    {**f["power"], "max_voltage_V": volt},
                            "adhesion": {**f["adhesion"], "pad_area_um2": pad}},
                 "stack": state.get("stack", {}), "seed": seed}

        else:
            s = {**state, "seed": seed}

        try:
            r = kc.simulate(layer, s, seed=seed)
            metrics = extract_metrics(layer, r)
            if model_unc > 0.0:
                # Even after phi bias-correction, the TRUE value can differ from
                # the sim by ~model_unc (relative). Perturb each metric so a
                # near-threshold candidate on a poorly-trusted model fails more
                # often — the search then prefers recipes with margin against
                # simulator error, not just against fab variation.
                metrics = {k: (v * (1.0 + random.gauss(0, model_unc))
                               if isinstance(v, (int, float)) and not isinstance(v, bool)
                               else v)
                           for k, v in metrics.items()}
            if passes_thresholds(layer, metrics):
                passed += 1
            else:
                for metric, (op, threshold) in PROMOTION_THRESHOLDS.get(layer, {}).items():
                    val = metrics.get(metric)
                    if val is None:
                        continue
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        continue
                    failed = (op == "ge" and val < threshold) or (op == "le" and val > threshold)
                    if failed:
                        fail_counts[metric] = fail_counts.get(metric, 0) + 1
        except Exception:
            fail_counts["sim_error"] = fail_counts.get("sim_error", 0) + 1

    yield_frac = passed / n_samples
    return yield_frac, fail_counts


def print_mc_results(layer, n_samples, yield_frac, fail_counts):
    print(f"\n{'='*70}")
    print(f"  Monte Carlo Yield — Layer {layer}  ({n_samples} samples)")
    print(f"{'='*70}")
    print(f"  Predicted yield: {yield_frac*100:.1f}%  "
          f"({int(yield_frac*n_samples)}/{n_samples} pass all thresholds)")
    print()
    print(f"  Failure breakdown (% of failing trials):")
    total_fail = n_samples - int(yield_frac * n_samples)
    if total_fail > 0:
        for metric, count in sorted(fail_counts.items(), key=lambda x: -x[1]):
            print(f"    {metric:35s}: {count:4d} failures ({count/n_samples*100:5.1f}%)")
    else:
        print("    No failures detected.")
    print()
    thresholds = PROMOTION_THRESHOLDS.get(layer, {})
    if thresholds:
        print("  Thresholds applied:")
        for metric, (op, val) in thresholds.items():
            op_str = ">=" if op == "ge" else "<="
            print(f"    {metric:35s}: {op_str} {val}")


# ---------------------------------------------------------------------------
# 3. Pareto Front Mapper
# ---------------------------------------------------------------------------

def sweep_pareto_L(kc, n_points=200, seed=42):
    """Sweep In fraction while holding O at stoichiometry. Returns Pareto data."""
    print(f"\n{'='*70}")
    print("  Pareto Front — Layer L  (In fraction sweep, O fixed stoichiometric)")
    print(f"  Objectives: mobility_cm2_Vs vs crystallization_risk")
    print(f"{'='*70}")

    results = []
    for i in range(n_points):
        f_In  = 0.05 + i * (0.90 / n_points)
        f_Ga  = max(0.40 - f_In * 0.30, 0.02)
        f_Zn  = max(0.25 - f_In * 0.15, 0.02)
        metal_total = f_In + f_Ga + f_Zn
        O_stoich = f_In * 1.5 + f_Ga * 1.5 + f_Zn * 1.0
        total = metal_total + O_stoich

        comp = {
            "In": f_In / total,
            "Ga": f_Ga / total,
            "Zn": f_Zn / total,
            "O":  O_stoich / total,
        }
        state = {"materials": {"channel_composition": comp}, "seed": seed}
        try:
            r = kc.simulate("L", state, seed=seed)
            m = extract_metrics("L", r)
            results.append({
                "f_In": round(f_In, 3),
                "f_Ga": round(f_Ga, 3),
                "mobility": m.get("mobility_cm2_Vs", 0),
                "cryst_risk": m.get("crystallization_risk", 1),
                "Ioff": m.get("Ioff_A", 1),
                "SS":   m.get("SS_mV_dec", 999),
            })
        except Exception:
            pass

    # Find Pareto-optimal (high mobility, low cryst_risk)
    print(f"\n  {'f_In':>6} {'f_Ga':>6} {'μ':>8} {'cryst':>8} {'Ioff':>12} {'SS':>8}")
    print("  " + "-" * 56)

    # Print a representative sample (every 10th point)
    for r in results[::10]:
        tag = " ← PARETO" if r["cryst_risk"] < 0.3 and r["mobility"] > 8.0 else ""
        print(f"  {r['f_In']:6.3f} {r['f_Ga']:6.3f} {r['mobility']:8.3f} "
              f"{r['cryst_risk']:8.3f} {r['Ioff']:12.2e} {r['SS']:8.2f}{tag}")

    # Summary
    best_mob = max(results, key=lambda x: x["mobility"])
    best_bal = max(results, key=lambda x: x["mobility"] / max(x["cryst_risk"], 0.01))
    print(f"\n  Best mobility:  f_In={best_mob['f_In']:.3f}, μ={best_mob['mobility']:.2f}")
    print(f"  Best balanced:  f_In={best_bal['f_In']:.3f}, μ={best_bal['mobility']:.2f}, "
          f"cryst={best_bal['cryst_risk']:.3f}")
    return results


def sweep_pareto_PM(kc, n_points=100, seed=42):
    """Sweep Ge doping fraction in Sb2Se3:Ge:Cl. Returns Pareto data."""
    print(f"\n{'='*70}")
    print("  Pareto Front — Layer PM  (Ge + Cl fraction sweep in Sb2Se3 base)")
    print(f"  Objectives: delta_n vs loss_k  (FOM = delta_n/k)")
    print(f"{'='*70}")

    results = []
    for i in range(n_points):
        ge_frac  = i * 0.25 / max(n_points - 1, 1)   # 0 to 0.25
        cl_frac  = ge_frac * 0.3                       # Cl scales with Ge

        formula  = f"Sb2Se3:Ge{ge_frac:.3f}:Cl{cl_frac:.4f}"
        state    = {"formula": formula, "seed": seed}
        try:
            r  = kc.simulate("PM", state, seed=seed)
            m  = extract_metrics("PM", r)
            results.append({
                "ge_frac":  round(ge_frac, 3),
                "cl_frac":  round(cl_frac, 4),
                "delta_n":  m.get("delta_n", 0),
                "loss_k":   m.get("loss_k",  1),
                "fom":      m.get("fom",     0),
            })
        except Exception:
            pass

    print(f"\n  {'Ge frac':>8} {'Cl frac':>8} {'Δn':>8} {'k':>12} {'FOM':>10}")
    print("  " + "-" * 52)
    for r in results[::max(len(results)//15, 1)]:
        print(f"  {r['ge_frac']:8.3f} {r['cl_frac']:8.4f} "
              f"{r['delta_n']:8.4f} {r['loss_k']:12.6f} {r['fom']:10.1f}")

    if results:
        best = max(results, key=lambda x: x["fom"])
        print(f"\n  Best FOM: Ge={best['ge_frac']:.3f}, Cl={best['cl_frac']:.4f}, "
              f"Δn={best['delta_n']:.4f}, k={best['loss_k']:.6f}, FOM={best['fom']:.1f}")
    return results


def sweep_pareto_E(kc, n_points=50, seed=42):
    """Sweep Zr fraction in HZO. Returns Pareto data."""
    print(f"\n{'='*70}")
    print("  Pareto Front — Layer E  (Zr fraction sweep, 10 nm, 450°C)")
    print(f"  Objectives: polarization_uC_cm2 vs dielectric_constant_k")
    print(f"{'='*70}")

    results = []
    for i in range(n_points):
        x_Zr = 0.01 + i * 0.98 / max(n_points - 1, 1)
        x_Hf = round(1.0 - x_Zr, 3)
        formula = f"Hf{x_Hf}Zr{round(x_Zr, 3)}O2"
        state = {"formula": formula, "thickness_nm": 10.0, "anneal_temp_C": 450.0, "seed": seed}
        try:
            r  = kc.simulate("E", state, seed=seed)
            m  = extract_metrics("E", r)
            pol = float(m.get("polarization_uC_cm2", 0))
            k   = float(m.get("dielectric_constant_k", 0))
            end = m.get("endurance_cycles", "0")
            results.append({"x_Zr": round(x_Zr, 3), "pol": pol, "k": k, "endurance": end})
        except Exception:
            pass

    print(f"\n  {'x_Zr':>6} {'Pol µC/cm²':>12} {'k':>8} {'Endurance':>12}")
    print("  " + "-" * 44)
    for r in results[::max(len(results)//10, 1)]:
        print(f"  {r['x_Zr']:6.3f} {r['pol']:12.2f} {r['k']:8.1f} {r['endurance']:>12}")

    if results:
        best = max(results, key=lambda x: x["pol"])
        print(f"\n  Best Pr: x_Zr={best['x_Zr']:.3f}, Pr={best['pol']:.2f} µC/cm², "
              f"k={best['k']:.1f}")
    return results


def sweep_pareto_EM(kc, n_points=60, seed=42):
    """Sweep x_Sc from 0.10 to 0.42 on each substrate. Shows d33 vs sec_phase_risk."""
    print(f"\n{'='*70}")
    print("  Pareto Front — Layer EM  (Sc fraction sweep on three substrates)")
    print(f"  Objectives: d33_pC_N vs sec_phase_risk")
    print(f"{'='*70}")

    for substrate in ["Si", "SiC", "Al2O3"]:
        print(f"\n  Substrate: {substrate}")
        print(f"  {'x_Sc':>6} {'d33 (pC/N)':>12} {'kt2 (%)':>9} {'stab':>7} {'sec_risk':>9}")
        print("  " + "-" * 48)
        results = []
        for i in range(n_points):
            x_Sc = 0.10 + i * (0.42 - 0.10) / max(n_points - 1, 1)
            x_Al = round(1.0 - x_Sc, 3)
            formula = f"Sc{round(x_Sc, 3)}Al{x_Al}N"
            state = {"formula": formula, "substrate": substrate, "dep_temp_C": 450.0, "seed": seed}
            try:
                r = kc.simulate("EM", state, seed=seed)
                m = r.get("metrics", r)
                d33  = float(m.get("d33_pC_N", 0))
                kt2  = float(m.get("coupling_kt2_pct", 0))
                stab = float(m.get("_phase_stability", 0))
                risk = float(m.get("_sec_phase_risk", 1))
                results.append({"x_Sc": round(x_Sc, 3), "d33": d33, "kt2": kt2,
                                 "stab": stab, "risk": risk})
            except Exception:
                pass

        for r in results[::max(len(results) // 10, 1)]:
            tag = " ← RECOMMENDED" if r["d33"] > 14.0 and r["risk"] < 0.5 else ""
            print(f"  {r['x_Sc']:6.3f} {r['d33']:12.2f} {r['kt2']:9.2f} "
                  f"{r['stab']:7.3f} {r['risk']:9.3f}{tag}")

        if results:
            best = max(results, key=lambda x: x["d33"] * (1.0 - 0.5 * x["risk"]))
            print(f"  Best balanced: x_Sc={best['x_Sc']:.3f}, d33={best['d33']:.2f} pC/N, "
                  f"risk={best['risk']:.3f}")


# ---------------------------------------------------------------------------
# Process control spec
# ---------------------------------------------------------------------------

def print_process_spec(layer, jacobian, sigmas):
    """Rank variables by their impact = |∂metric/∂xi| × σ_i."""
    key_metrics = {
        "L": ["mobility_cm2_Vs", "crystallization_risk", "Ioff_A"],
        "PM": ["delta_n", "loss_k", "fom"],
        "E": ["polarization_uC_cm2", "dielectric_constant_k"],
        "EM": ["d33_pC_N", "coupling_kt2_pct"],
    }.get(layer, [])

    print(f"\n{'='*70}")
    print(f"  Process Control Specification — Layer {layer}")
    print(f"  Impact = |∂metric/∂variable| × process_sigma")
    print(f"  Higher impact = must control this variable more tightly")
    print(f"{'='*70}")

    layer_sigmas = sigmas.get(layer, {})
    impact_table = []
    for var, sensitivities in jacobian.items():
        sigma = layer_sigmas.get(var, 0.02)
        for metric in key_metrics:
            sens = sensitivities.get(metric, 0.0)
            impact = abs(sens) * sigma
            impact_table.append((var, metric, sens, sigma, impact))

    impact_table.sort(key=lambda x: -x[4])

    print(f"  {'Variable':12s} {'Metric':30s} {'Sensitivity':>12} {'σ_process':>10} {'Impact':>10}")
    print("  " + "-" * 78)
    for var, metric, sens, sigma, impact in impact_table[:20]:
        priority = "  *** CRITICAL" if impact > 0.5 else ("  ** HIGH" if impact > 0.1 else "")
        print(f"  {var:12s} {metric:30s} {sens:+12.4f} {sigma:10.4f} {impact:10.4f}{priority}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Morphium Sensitivity Analysis")
    parser.add_argument("--layer", choices=["L", "PM", "E", "EM"], help="Layer to analyse")
    parser.add_argument("--all", action="store_true", help="Analyse all layers")
    parser.add_argument("--jacobian", action="store_true", default=True,
                        help="Compute numerical Jacobian (default: on)")
    parser.add_argument("--mc", action="store_true", help="Run Monte Carlo yield")
    parser.add_argument("--mc-samples", type=int, default=1000, metavar="N",
                        help="Number of Monte Carlo samples (default: 1000)")
    parser.add_argument("--pareto", action="store_true", help="Map Pareto front")
    parser.add_argument("--full", action="store_true",
                        help="Run all analyses (Jacobian + MC + Pareto)")
    parser.add_argument("--root", default=".", help="Project root directory")
    args = parser.parse_args()

    # Initialise kernel (path relative to project root)
    kc_root = os.path.join(args.root, ".")
    kc = KernelClient(project_root=kc_root)

    if args.full:
        args.mc = True
        args.pareto = True

    layers = []
    if args.all:
        layers = ["L", "PM", "E", "EM"]
    elif args.layer:
        layers = [args.layer]
    else:
        parser.print_help()
        print("\nError: specify --layer LAYER or --all")
        sys.exit(1)

    random.seed(999)   # reproducible MC

    for layer in layers:
        print(f"\n{'#'*70}")
        print(f"  LAYER {layer}")
        print(f"{'#'*70}")

        state = CHAMPIONS.get(layer, {})

        # --- Jacobian ---
        print(f"\nRunning Jacobian analysis for Layer {layer}...")
        base_metrics, jacobian = compute_jacobian(kc, layer, state)
        print_jacobian(layer, base_metrics, jacobian)
        print_process_spec(layer, jacobian, PROCESS_SIGMA)

        # --- Monte Carlo ---
        if args.mc:
            print(f"\nRunning Monte Carlo ({args.mc_samples} samples) for Layer {layer}...")
            yield_frac, fail_counts = run_monte_carlo(kc, layer, state, n_samples=args.mc_samples)
            print_mc_results(layer, args.mc_samples, yield_frac, fail_counts)

        # --- Pareto ---
        if args.pareto:
            if layer == "L":
                sweep_pareto_L(kc)
            elif layer == "PM":
                sweep_pareto_PM(kc)
            elif layer == "E":
                sweep_pareto_E(kc)
            elif layer == "EM":
                sweep_pareto_EM(kc)

    print(f"\n{'='*70}")
    print("  Analysis complete.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
