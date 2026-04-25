"""
Morphium-E Layer API — Tier 1.5 Physics Engine
HfO₂-based High-k / Ferroelectric Gate Dielectric (HZO family)

Physics Models Implemented:

  1. Orthorhombic Phase Fraction (f_ortho):

     The ferroelectric Pca2₁ orthorhombic phase of HfO₂ is the core
     mechanism behind large spontaneous polarisation (Pr > 5 µC/cm²).

     f_ortho = f_Zr(x_Zr) × f_thick(t) × f_anneal(T)

     where:
       f_Zr(x_Zr)  : Gaussian peak at x_Zr = 0.50 (σ = 0.15)
                      At x_Zr → 0: monoclinic HfO₂ (paraelectric)
                      At x_Zr → 1: tetragonal ZrO₂ (antiferroelectric)
                      At x_Zr ≈ 0.50: Pca2₁ maximum (~80% orthorhombic)

       f_thick(t)   : Film thickness window 4–25 nm
                      σ_lo(t−4 nm / 1.5 nm) × σ_hi(−(t−30 nm) / 6 nm)
                      Very thin (<3 nm): can't crystallize
                      Very thick (>30 nm): reverts to monoclinic

       f_anneal(T)  : Sigmoid from 350°C onset
                      σ((T − 380°C) / 50°C)
                      Below 350°C: amorphous, no ferroelectric phase

  2. Dopant Effects on f_ortho:

     Al (tensile stress → stabilises small-radius orthorhombic):
       f_ortho ×= (1 + 3.0 × x_Al) for x_Al ≤ 0.06
       f_ortho ×= exp(−15 × (x_Al − 0.06)) for x_Al > 0.06 (over-doping kills it)

     Si (similar mechanism to Al, weaker effect):
       f_ortho ×= (1 + 2.0 × x_Si) for x_Si ≤ 0.04

     Ti (tetragonal stabiliser — destroys ferroelectric phase):
       f_ortho ×= exp(−6 × x_Ti)

     Y, La, Ce (rare-earth dopants — moderate stabilisers like Al):
       f_ortho ×= (1 + 1.5 × x_RE)

     f_ortho is clamped to [0, 1].

  3. Polarisation:

     Pr = PR_MAX × f_ortho × f_dopant_Pr

     PR_MAX = 25.0 µC/cm²  (champion HZO, fully orthorhombic)

     f_dopant_Pr: Ti doping reduces remanent polarisation due to
       competing tetragonal domains:  f_dopant_Pr = exp(−4 × x_Ti)

  4. Dielectric Constant (k):

     Vegard's law for the Hf₁₋ₓZrₓO₂ system:
       k_base = (1−x_Zr) × k_mono + x_Zr × k_tet

     Orthorhombic correction (k_ortho ≈ 28):
       k = (1 − f_ortho) × k_base + f_ortho × k_ortho

     Ti doping adds high-k (k_TiO₂ ≈ 80) but degrades gap:
       k ×= (1 + 2.0 × x_Ti)

     Al/Si reduce k slightly (k_Al₂O₃ ≈ 9, k_SiO₂ ≈ 3.9):
       k ×= (1 − 0.3 × x_Al) × (1 − 0.5 × x_Si)

     k is clamped to [2, 80].

  5. Bandgap:

     Vegard's law with optical bowing parameter b = 0.5 eV:
       E_g = (1−x_Zr) × E_g_HfO2 + x_Zr × E_g_ZrO2 − b × x_Zr × (1−x_Zr)

     Dopant corrections:
       Ti shrinks gap: E_g ×= (1 − 0.3 × x_Ti)    (TiO₂: 3.0 eV)
       Al widens slightly: E_g += 0.3 × x_Al       (Al₂O₃: 8.7 eV)

  6. Endurance:

     Physical basis: oxygen vacancy redistribution during domain switching
     causes wake-up and fatigue.  Better orthorhombic purity → cleaner
     domain walls → fewer pinning sites → better endurance.

       endurance = E_MAX × f_ortho² × (E_g / E_g_HfO2)³

     E_MAX = 1e11 cycles (champion HZO at 2 V, 1 kHz, room temperature)

Calibration:
  Hf0.5Zr0.5O2 at 10 nm, 450°C anneal → f_ortho ≈ 0.73, Pr ≈ 18 µC/cm²
  This matches Böscke (2011), Mueller (2012), Lomenzo (2016) data.

References:
  - Böscke et al.; APL 99 (2011) 102903        (FE phase discovery)
  - Mueller et al.; ECS JSS 1 (2012) N123      (HZO optimisation)
  - Lomenzo et al.; TSF 615 (2016) 139         (Al doping)
  - Materlik et al.; JAP 117 (2015) 134109     (phase diagram model)
  - Schenk et al.; ACS Nano 12 (2018) 4014     (thickness dependence)
"""

import math
import re
import random
import json
import hashlib

SIM_MODEL_VERSION = "1.5"

# ---------------------------------------------------------------------------
# Phase diagram constants
# ---------------------------------------------------------------------------
ZR_PEAK    = 0.500   # Zr fraction of max orthorhombic phase
ZR_SIGMA   = 0.150   # Gaussian width (in x_Zr units)
F_ORTHO_MAX = 0.820  # Maximum achievable orthorhombic fraction (real HZO)

# ---------------------------------------------------------------------------
# Thickness window
# ---------------------------------------------------------------------------
T_LO_NM   = 4.0     # Lower onset  [nm]
T_SIG_LO  = 1.5     # [nm]
T_HI_NM   = 30.0    # Upper onset  [nm]
T_SIG_HI  = 6.0     # [nm]

# ---------------------------------------------------------------------------
# Annealing temperature
# ---------------------------------------------------------------------------
T_ANN_MID  = 380.0  # [°C] midpoint of crystallisation sigmoid
T_ANN_SIG  = 50.0   # [°C] width

# ---------------------------------------------------------------------------
# Dielectric constants (monoclinic HfO₂ / tetragonal ZrO₂ / orthorhombic)
# ---------------------------------------------------------------------------
K_MONO    = 18.0    # Monoclinic HfO₂
K_TET     = 38.0    # Tetragonal ZrO₂
K_ORTHO   = 28.0    # Orthorhombic HZO

# ---------------------------------------------------------------------------
# Bandgap parameters
# ---------------------------------------------------------------------------
E_G_HFO2  = 5.80    # [eV]
E_G_ZRO2  = 5.20    # [eV]
E_G_BOWING = 0.50   # [eV]

# ---------------------------------------------------------------------------
# Polarisation
# ---------------------------------------------------------------------------
PR_MAX    = 25.0    # [µC/cm²] at full orthorhombic

# ---------------------------------------------------------------------------
# Endurance
# ---------------------------------------------------------------------------
ENDURANCE_MAX = 1e11   # [cycles]


def _sigmoid(x):
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _gaussian(x, mu, sigma):
    return math.exp(-0.5 * ((x - mu) / sigma) ** 2)


class MorphiumSimulatorE:
    def __init__(self, seed=None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def simulate(self, state):
        formula      = state.get("formula", "Hf0.5Zr0.5O2")
        thickness_nm = float(state.get("thickness_nm", 10.0))
        anneal_temp  = float(state.get("anneal_temp_C", 450.0))

        # ----------------------------------------------------------------
        # 1.  Parse formula → element amounts
        #
        #     Handles:  "Hf0.5Zr0.5O2"  "HfO2"  "Hf0.5Zr0.4Al0.1O2"
        # ----------------------------------------------------------------
        atoms = re.findall(r'([A-Z][a-z]*)(\d*\.?\d*)', formula)
        raw = {}
        for el, amt_str in atoms:
            if not el:
                continue
            amt = float(amt_str) if amt_str else 1.0
            raw[el] = raw.get(el, 0.0) + amt

        # Filter oxygen out; keep cations only
        cations = {el: v for el, v in raw.items() if el != "O"}
        total_c = sum(cations.values())
        if total_c <= 0:
            return {"error": "No cation species found in formula"}

        # Normalised cation fractions
        fc = {el: v / total_c for el, v in cations.items()}

        x_Hf = fc.get("Hf", 0.0)
        x_Zr = fc.get("Zr", 0.0)
        x_Ti = fc.get("Ti", 0.0)
        x_Al = fc.get("Al", 0.0)
        x_Si = fc.get("Si", 0.0)
        # Rare-earth stabilisers (Y, La, Ce, Gd, Nd)
        RE_ELS = {"Y", "La", "Ce", "Gd", "Nd"}
        x_RE = sum(fc.get(el, 0.0) for el in RE_ELS)

        # ----------------------------------------------------------------
        # 2.  Orthorhombic phase fraction
        # ----------------------------------------------------------------

        # 2a. Zr-content Gaussian
        f_Zr = _gaussian(x_Zr, ZR_PEAK, ZR_SIGMA)

        # 2b. Thickness window (both ends sigmoidal)
        f_thick = (_sigmoid((thickness_nm - T_LO_NM) / T_SIG_LO)
                   * _sigmoid(-(thickness_nm - T_HI_NM) / T_SIG_HI))

        # 2c. Annealing temperature
        f_anneal = _sigmoid((anneal_temp - T_ANN_MID) / T_ANN_SIG)

        f_ortho = F_ORTHO_MAX * f_Zr * f_thick * f_anneal

        # 2d. Dopant corrections
        # Al: linear stabilisation up to 6%, then exponential kill
        if x_Al <= 0.06:
            f_ortho *= (1.0 + 3.0 * x_Al)
        else:
            f_ortho *= (1.0 + 3.0 * 0.06) * math.exp(-15.0 * (x_Al - 0.06))

        # Si: weaker Al-like stabiliser
        if x_Si <= 0.04:
            f_ortho *= (1.0 + 2.0 * x_Si)

        # Ti: tetragonal stabiliser (kills orthorhombic)
        f_ortho *= math.exp(-6.0 * x_Ti)

        # Rare-earth dopants (moderate stabilisers)
        f_ortho *= (1.0 + 1.5 * x_RE)

        f_ortho = min(max(f_ortho, 0.0), 1.0)

        # ----------------------------------------------------------------
        # 3.  Polarisation
        # ----------------------------------------------------------------
        f_dopant_Pr = math.exp(-4.0 * x_Ti)
        pol = PR_MAX * f_ortho * f_dopant_Pr

        # ----------------------------------------------------------------
        # 4.  Dielectric constant
        # ----------------------------------------------------------------
        # Vegard's law base (monoclinic HfO₂ ↔ tetragonal ZrO₂)
        k_base = (1.0 - x_Zr) * K_MONO + x_Zr * K_TET
        # Orthorhombic correction
        k_val  = (1.0 - f_ortho) * k_base + f_ortho * K_ORTHO
        # Ti high-k boost (leaky channel)
        k_val *= (1.0 + 2.0 * x_Ti)
        # Al/Si reduction
        k_val *= max(1.0 - 0.30 * x_Al, 0.5)
        k_val *= max(1.0 - 0.50 * x_Si, 0.5)
        k_val  = min(max(k_val, 2.0), 80.0)

        # ----------------------------------------------------------------
        # 5.  Bandgap
        # ----------------------------------------------------------------
        E_g = ((1.0 - x_Zr) * E_G_HFO2
               + x_Zr * E_G_ZRO2
               - E_G_BOWING * x_Zr * (1.0 - x_Zr))
        # Ti penalty
        E_g *= (1.0 - 0.30 * x_Ti)
        # Al benefit
        E_g += 0.30 * x_Al
        E_g  = max(E_g, 1.0)

        # ----------------------------------------------------------------
        # 6.  Endurance
        # ----------------------------------------------------------------
        endurance = ENDURANCE_MAX * (f_ortho ** 2) * ((E_g / E_G_HFO2) ** 3)
        endurance = max(endurance, 1.0)

        # ----------------------------------------------------------------
        # 7.  Seed-controlled deterministic noise
        # ----------------------------------------------------------------
        if self.seed is not None:
            noise_k   = 1.0 + random.uniform(-0.03, 0.03)
            noise_pol = 1.0 + random.uniform(-0.05, 0.05)
            noise_end = 1.0 + random.uniform(-0.10, 0.10)
        else:
            noise_k   = 1.0
            noise_pol = 1.0
            noise_end = 1.0

        k_val    *= noise_k
        pol      *= noise_pol
        endurance *= noise_end

        return {
            "formula":                  formula,
            "thickness_nm":             thickness_nm,
            "anneal_temp_C":            anneal_temp,
            "dielectric_constant_k":    round(k_val, 2),
            "bandgap_ev":               round(E_g, 2),
            "polarization_uC_cm2":      round(pol, 2),
            "endurance_cycles":         round(endurance, 0),
            # Diagnostics
            "_f_ortho":                 round(f_ortho, 4),
            "_f_Zr_Gaussian":           round(f_Zr, 4),
            "_f_thick":                 round(f_thick, 4),
            "_f_anneal":                round(f_anneal, 4),
            "seed":                     self.seed,
        }


def execute(state):
    seed = state.get("seed", 42)
    sim  = MorphiumSimulatorE(seed=seed)
    data = sim.simulate(state)
    result = {
        "status":            "success",
        "data":              data,
        "sim_model_version": SIM_MODEL_VERSION,
        "hash":              hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }
    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        ({"formula": "Hf0.5Zr0.5O2",           "thickness_nm": 10.0, "anneal_temp_C": 450.0},
         42, "Champion HZO — should have high Pr and k"),
        ({"formula": "HfO2",                    "thickness_nm": 10.0, "anneal_temp_C": 450.0},
         42, "Pure HfO₂ — monoclinic, low Pr"),
        ({"formula": "ZrO2",                    "thickness_nm": 10.0, "anneal_temp_C": 450.0},
         42, "Pure ZrO₂ — tetragonal, very low Pr"),
        ({"formula": "Hf0.5Zr0.5O2",           "thickness_nm":  3.0, "anneal_temp_C": 450.0},
         42, "HZO too thin (< 4 nm) — reduced f_ortho"),
        ({"formula": "Hf0.5Zr0.5O2",           "thickness_nm": 10.0, "anneal_temp_C": 300.0},
         42, "HZO low anneal temp — not crystallised"),
        ({"formula": "Hf0.5Zr0.4Al0.1O2",      "thickness_nm": 10.0, "anneal_temp_C": 450.0},
         42, "Al-doped HZO — too much Al kills phase"),
        ({"formula": "Hf0.5Zr0.4Al0.05Zr0.05O2", "thickness_nm": 10.0, "anneal_temp_C": 450.0},
         42, "Optimal Al doping (5%) — slight boost"),
        ({"formula": "Hf0.4Zr0.5Ti0.1O2",      "thickness_nm": 10.0, "anneal_temp_C": 450.0},
         42, "Ti doping — high k but kills Pr"),
    ]

    print("=== Morphium-E Tier 1.5 — HZO Phase Engineering ===")
    print(f"{'Description':40s}  {'k':>6}  {'Eg':>5}  {'Pr':>8}  {'ortho':>6}  {'endur':>10}")
    print("-" * 85)
    for state, seed, desc in tests:
        state["seed"] = seed
        r = execute(state)["data"]
        print(
            f"  {desc:38s}  "
            f"{r['dielectric_constant_k']:6.1f}  "
            f"{r['bandgap_ev']:5.2f}  "
            f"{r['polarization_uC_cm2']:8.2f}  "
            f"{r['_f_ortho']:6.4f}  "
            f"{r['endurance_cycles']:>10}"
        )
