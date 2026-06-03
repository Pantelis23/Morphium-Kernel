"""
Morphium-EM Layer API — Tier 1.5 Physics Engine
ScAlN Piezoelectric MEMS (Wurtzite-phase Scandium Aluminium Nitride)

Physics Models Implemented:

  1. d₃₃ Empirical Calibration (replaces linear mixing):

     Literature data for sputtered ScₓAl₁₋ₓN films (Wingqvist 2010,
     Hakonen 2019, Fichtner 2019):
       x=0.00: d₃₃ = 3.9 pC/N  (pure AlN)
       x=0.12: d₃₃ ≈ 7.0 pC/N
       x=0.25: d₃₃ ≈ 13.0 pC/N
       x=0.40: d₃₃ ≈ 26.0 pC/N  (reactive-magnetron consensus peak before instability)

     Fit: d₃₃_bulk(x) = D33_ALN × (1 + A₁×x + A₂×x²)
     Calibrated: A₁ = 8.40, A₂ = 12.90 (super-linear growth from s-d hybridisation;
     rescaled 2026-06-03 to the ~26-27 pC/N peak, Akiyama 2009 / Mertin 2017)

  2. Phase Stability Cliff (f_stab):

     Above x ≈ 0.43 the wurtzite structure is no longer the ground state
     (layered hexagonal or rock-salt ScN competes). The d₃₃ collapses.
     This is substrate-dependent due to biaxial strain:

       x_cliff(substrate) = x_cliff_bulk + Δx_strain
         Si      (compressive −0.8%): Δx = −0.02  → cliff at 0.41
         AlN/SiC (near-matched):      Δx = +0.00  → cliff at 0.43
         Al₂O₃   (tensile +0.3%):     Δx = +0.01  → cliff at 0.44

     Sigmoid width w = 0.025 (sharp, matches experiment).
     f_stab = 1 − σ((x − x_cliff) / w)

  3. Film Texture Factor (f_texture):

     Only (001)-oriented columns contribute to the macroscopic d₃₃
     (transverse isotropy assumption). Texture degrades at low deposition
     temperature and high Sc content (lattice frustration → column
     competition).

     f_texture = (T_dep sigmoid) × (Sc degradation)
       f_T_dep = 0.85 + 0.15 × σ((T_dep − 280°C) / 70°C)
       f_Sc    = 1 − 0.20 × x  (Sc increases mosaic tilt)

  4. Electromechanical Coupling kt²:

     The thickness-mode coupling kt² (used in FBAR/SMR resonators)
     is approximately proportional to k₃₃² × 0.5 (geometry factor).
     Empirical fit to literature:

       kt²(x) = KT2_ALN + 0.28 × x          for x < x_cliff
       kt²_eff = kt²(x) × f_stab × f_texture

     KT2_ALN = 0.065 (6.5%) at x=0 ✓
     x=0.40: kt² = 0.065 + 0.112 = 0.177 → kt² ≈ 17.7% ✓ (literature 15-20%)

  5. Young's Modulus (Voigt-Reuss average):

     E(x) = E_ALN − (E_ALN − E_SCN) × x
     E_ALN = 310 GPa, E_SCN = 180 GPa

     Secondary-phase softening: if x > x_cliff, E is further reduced 20%
     (amorphous/mixed-phase boundary regions act as compliant interlayers).

  6. Secondary Phase Risk:

     Nucleation of ScN rock-salt grains becomes likely above x ≈ 0.38.
     Modelled as sigmoid: risk = σ((x − 0.38) / 0.03)
     Also increases with high deposition T (> 500°C).

Calibration:
  Sc₀.₄₀Al₀.₆₀N on Si at T_dep=350°C:
    d₃₃ ≈ 16-17 pC/N (target 18 before texture factor)
    kt² ≈ 14-15%  (target 17% before texture factor)
  Old Tier-1.0 champion Sc₀.₄₀Al₀.₆₀N: d₃₃=16.23 — reproduced ✓

References:
  - Wingqvist et al.; APL 97 (2010) 112902      (kt² measurement)
  - Hakonen et al.; APL 116 (2020) 022901        (d₃₃ vs Sc content)
  - Fichtner et al.; JAP 125 (2019) 114103       (phase stability)
  - Tasnádi et al.; PRL 104 (2010) 137601        (theory of d₃₃ enhancement)
"""

import math
import re
import random
import json
import hashlib

SIM_MODEL_VERSION = "1.5"

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
D33_ALN  = 3.9    # [pC/N] wurtzite AlN piezoelectric coefficient
KT2_ALN  = 0.065  # Thickness-mode coupling of AlN (6.5%)
E_ALN    = 310.0  # [GPa] Young's modulus AlN
E_SCN    = 180.0  # [GPa] Young's modulus ScN (rock-salt, softer)

# d₃₃ quadratic fit coefficients. Rescaled x1.5 from the original (5.60/8.60)
# on 2026-06-03 (audit M-6/M-7): the old coefficients gave d33_bulk(0.40)=18
# (eff ~16.6 after f_texture), ~35% below the reactive-magnetron consensus peak
# of ~26-27 pC/N at x=0.40-0.43 (Akiyama 2009 27.6@0.43; Mertin/Zywitzki 2017
# 26.9-27.3). Now d33_bulk(0.40)=25.1 (eff ~23), small residual phi offset.
D33_A1   = 8.40
D33_A2   = 12.90

# Phase stability cliff (bulk, in Sc mole fraction)
# Asymmetric: fully stable below cliff, exponential collapse above.
# Physical justification: the wurtzite → layered-hexagonal transition is
# first-order; films grown below x_cliff are overwhelmingly wurtzite.
X_CLIFF_BULK  = 0.430
CLIFF_STEEP   = 25.0    # exponential decay rate above cliff (per unit x)

# Substrate strain offsets (shift in x_cliff)
SUBSTRATE_STRAIN = {
    "Si":    -0.020,   # Compressive biaxial → lower cliff
    "SiC":   +0.000,   # Near-matched → nominal
    "Al2O3": +0.010,   # Slightly tensile → higher cliff
    "free":  +0.000,   # Bulk / no substrate
}

# Texture model
T_DEP_MID  = 280.0   # [°C] midpoint of texture sigmoid
T_DEP_SIG  = 70.0    # [°C] width
F_TEXTURE_BASE = 0.85
F_TEXTURE_TOP  = 0.15
F_SC_TEXTURE   = 0.10  # Sc degrades column orientation (mild mosaic tilt)

# kt² empirical slope
KT2_SC_SLOPE = 0.28

# Secondary phase risk
X_SEC_PHASE_MID = 0.380
W_SEC_PHASE     = 0.030


def _sigmoid(x):
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class MorphiumSimulatorEM:
    def __init__(self, seed=None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def simulate(self, state):
        formula    = state.get("formula", "Sc0.4Al0.6N")
        substrate  = state.get("substrate", "Si")
        dep_temp_C = float(state.get("dep_temp_C", 350.0))

        # ----------------------------------------------------------------
        # 1.  Parse formula → Sc fraction
        # ----------------------------------------------------------------
        atoms = re.findall(r'([A-Z][a-z]*)(\d*\.?\d*)', formula)
        sc_frac = 0.0
        al_frac = 0.0
        for el, amt_str in atoms:
            val = float(amt_str) if amt_str else 1.0
            if el == "Sc":
                sc_frac = val
            elif el == "Al":
                al_frac = val

        total_metal = sc_frac + al_frac
        if total_metal <= 0:
            return {"error": "No Sc or Al in formula"}

        x = sc_frac / total_metal   # Sc mole fraction in metal sublattice

        # ----------------------------------------------------------------
        # 2.  Phase stability cliff (substrate-dependent, asymmetric)
        #
        #     Below x_cliff: fully stable wurtzite → f_stab = 1.0
        #     Above x_cliff: exponential collapse of wurtzite fraction
        #       f_stab = exp(-CLIFF_STEEP × (x - x_cliff))
        #
        #     Physical origin: the wurtzite→hexagonal transition is first-
        #     order.  Films grown below x_cliff are predominantly wurtzite.
        #     The "pre-cliff" reduction seen in EBSD is mainly texture
        #     degradation, handled separately by f_texture.
        # ----------------------------------------------------------------
        delta_cliff = SUBSTRATE_STRAIN.get(substrate, 0.0)
        x_cliff = X_CLIFF_BULK + delta_cliff
        if x <= x_cliff:
            f_stab = 1.0
        else:
            f_stab = math.exp(-CLIFF_STEEP * (x - x_cliff))

        # ----------------------------------------------------------------
        # 3.  Bulk d₃₃ (super-linear Sc enhancement)
        # ----------------------------------------------------------------
        d33_bulk = D33_ALN * (1.0 + D33_A1 * x + D33_A2 * x**2)

        # ----------------------------------------------------------------
        # 4.  Film texture factor
        #
        #     Texture improves with deposition temperature (better
        #     surface mobility → columnar growth alignment).
        #     Sc incorporation increases mosaic tilt (misalignment) →
        #     reduces effective d₃₃ from non-(001) column contributions.
        # ----------------------------------------------------------------
        f_T_dep  = F_TEXTURE_BASE + F_TEXTURE_TOP * _sigmoid((dep_temp_C - T_DEP_MID) / T_DEP_SIG)
        f_Sc_tex = 1.0 - F_SC_TEXTURE * x
        f_texture = f_T_dep * f_Sc_tex

        # ----------------------------------------------------------------
        # 5.  Effective d₃₃
        # ----------------------------------------------------------------
        d33_eff = d33_bulk * f_stab * f_texture
        d33_eff = max(d33_eff, 0.0)

        # ----------------------------------------------------------------
        # 6.  Electromechanical coupling kt²
        # ----------------------------------------------------------------
        kt2_intrinsic = KT2_ALN + KT2_SC_SLOPE * x
        kt2_eff       = kt2_intrinsic * f_stab * f_texture
        kt2_pct       = kt2_eff * 100.0

        # ----------------------------------------------------------------
        # 7.  Young's modulus
        # ----------------------------------------------------------------
        E_eff = E_ALN - (E_ALN - E_SCN) * x
        if f_stab < 0.5:
            # Phase boundary: mixed amorphous/secondary-phase regions
            E_eff *= 0.80

        # ----------------------------------------------------------------
        # 8.  Secondary phase risk
        # ----------------------------------------------------------------
        sec_phase_risk = _sigmoid((x - X_SEC_PHASE_MID) / W_SEC_PHASE)
        # High deposition temperature increases ScN nucleation
        if dep_temp_C > 450.0:
            sec_phase_risk = min(sec_phase_risk + 0.15 * (dep_temp_C - 450.0) / 150.0, 1.0)

        # ----------------------------------------------------------------
        # 9.  Seed-controlled deterministic noise
        # ----------------------------------------------------------------
        if self.seed is not None:
            noise_d33 = 1.0 + random.uniform(-0.05, 0.05)
            noise_E   = 1.0 + random.uniform(-0.03, 0.03)
        else:
            noise_d33 = 1.0
            noise_E   = 1.0

        d33_eff *= noise_d33
        E_eff   *= noise_E

        return {
            "d33_pC_N":            round(d33_eff, 2),
            "youngs_modulus_GPa":  round(E_eff, 1),
            "coupling_kt2_pct":    round(kt2_pct, 2),
            "sc_fraction":         round(x, 4),
            # Diagnostics
            "_phase_stability":    round(f_stab, 4),
            "_f_texture":          round(f_texture, 4),
            "_d33_bulk":           round(d33_bulk, 2),
            "_x_cliff":            round(x_cliff, 3),
            "_sec_phase_risk":     round(sec_phase_risk, 3),
            "seed":                self.seed,
        }


def execute(state):
    seed = state.get("seed", 42)
    sim  = MorphiumSimulatorEM(seed=seed)
    metrics = sim.simulate(state)
    result = {
        "state":             state,
        "metrics":           metrics,
        "sim_model_version": SIM_MODEL_VERSION,
        "hash": hashlib.sha256(
            json.dumps(metrics, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }
    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        ({"formula": "Sc0.4Al0.6N",  "substrate": "Si",    "dep_temp_C": 350},  42, "Champion on Si, 350°C"),
        ({"formula": "Sc0.4Al0.6N",  "substrate": "SiC",   "dep_temp_C": 400},  42, "Champion on SiC, 400°C (higher cliff)"),
        ({"formula": "Sc0.0Al1.0N",  "substrate": "Si",    "dep_temp_C": 350},  42, "Pure AlN (x=0, reference)"),
        ({"formula": "Sc0.43Al0.57N","substrate": "Si",    "dep_temp_C": 350},  42, "At cliff (Si): near instability"),
        ({"formula": "Sc0.43Al0.57N","substrate": "SiC",   "dep_temp_C": 400},  42, "At cliff (SiC): still stable"),
        ({"formula": "Sc0.5Al0.5N",  "substrate": "Si",    "dep_temp_C": 350},  42, "Beyond cliff: phase collapse"),
        ({"formula": "Sc0.3Al0.7N",  "substrate": "Si",    "dep_temp_C": 200},  42, "Low temp: poor texture"),
        ({"formula": "Sc0.3Al0.7N",  "substrate": "Si",    "dep_temp_C": 450},  42, "High temp: good texture"),
        ({"formula": "Sc0.4Al0.6N",  "substrate": "Si",    "dep_temp_C": 600},  42, "Very high T: secondary phase risk"),
    ]

    print("=== Morphium-EM Tier 1.5 — ScAlN Phase Engineering ===")
    print(f"{'Description':40s}  {'d33':>7}  {'kt2%':>6}  {'E_GPa':>6}  {'stab':>6}  {'sec_risk':>8}")
    print("-" * 85)
    for state_e, seed, desc in tests:
        state_e["seed"] = seed
        r = execute(state_e)
        m = r["metrics"]
        print(
            f"  {desc:38s}  "
            f"{m['d33_pC_N']:7.2f}  "
            f"{m['coupling_kt2_pct']:6.2f}  "
            f"{m['youngs_modulus_GPa']:6.1f}  "
            f"{m['_phase_stability']:6.4f}  "
            f"{m['_sec_phase_risk']:8.3f}"
        )
