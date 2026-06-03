"""
Morphium-PM Layer API — Tier 1.5 Physics Engine
Phase-Change Photonics (Sb2Se3-family)

Physics Models Implemented:
  1. Clausius-Mossotti Effective-Medium Mixing (for refractive index):
       (n_eff² - 1)/(n_eff² + 2) = Σ_i f_i * (n_i² - 1)/(n_i² + 2)
     Applied separately to the crystalline and amorphous phases, giving
     n_cryst_eff and n_amorph_eff.  The phase-contrast figure is:
       delta_n = n_cryst_eff - n_amorph_eff
     This replaces the linear average dn_accum which ignores the
     non-linear polarisability relation between n and the local field.

  2. Moss Rule linking refractive index to bandgap:
       n_i^4 * E_g_i = 95  (empirical, Moss 1950, E_g in eV)
     Used as: n_i = (95 / E_g_i)^0.25
     This ties the optical properties to the electronic structure of
     each component — so changes in bandgap (e.g. from Ge doping)
     automatically propagate to n, rather than being hand-coded.

  3. Tauc–Urbach Extinction Model for loss k:
     In the sub-gap regime (E_photon < E_g) the absorption follows
     an exponential Urbach tail:
       k_eff = k_base * exp((E_photon - E_g_amorph) / E_U)
     where E_U is the Urbach energy (disorder parameter).
     A disorder floor k_floor prevents k → 0 for ideal compositions
     and represents unavoidable thin-film contributions (roughness,
     grain boundaries, defect clusters).

  4. Halogen Passivation via Urbach Energy Reduction:
     Cl/Br/F/I fill chalcogenide vacancy sites (e.g. missing Se),
     removing mid-gap dangling-bond states. The physical effect is a
     reduction in the Urbach energy E_U → E_U * (1 - passiv_factor),
     which steepens the absorption edge → lower k in the transparent
     window. This is the physically correct mechanism, not an ad-hoc
     loss subtraction.

  5. Chalcogenide Glass-Former Bonus (Ge + Sb + Se network):
     When Ge (4-fold, tetrahedral), Sb (3-fold, pyramidal) and Se
     (2-fold, chain-linking) are all present they form a stable
     covalent glass network (the GSST family). Benefits:
       a. More complete crystallisation → higher n_cryst → larger Δn
       b. More homogeneous amorphous phase → lower structural disorder
          → reduced E_U → lower k_amorph

Operating wavelength: λ = 1550 nm (telecom C-band)
  E_photon = hc/λ = 1240 / 1550 = 0.800 eV

Calibration notes:
  - Base Sb2Se3 at 1550 nm: Δn ~ 0.35-0.45 (amorph transparent, cryst absorbs)
  - With Ge doping + halogen: further Δn enhancement, k suppression
  - FOM = Δn / k; champion Sb2Se3:Ge:Cl expected FOM > 100 at 1550 nm
    (physically correct; old toy-model value of 81 at visible wavelengths
     underestimated the telecom-window advantage of this material class)

References:
  - Delaney et al.; Science Advances 7 (2021) eabg3500  (Sb2Se3 photonics)
  - Dong et al.; Adv. Funct. Mater. 29 (2019) 1806181  (GST FOM comparison)
  - Moss; Proc. Phys. Soc. B 63 (1950) 167             (Moss Rule)
  - Tauc, Grigorovici, Vancu; Phys. Status Solidi 15 (1966) 627
  - Urbach; Phys. Rev. 92 (1953) 1324                  (Urbach tail)
"""

import math
import re
import random
import json
import hashlib

SIM_MODEL_VERSION = "1.5"

# ---------------------------------------------------------------------------
# Operating conditions
# ---------------------------------------------------------------------------
E_PHOTON_EV = 0.800   # eV at λ = 1550 nm (telecom C-band)

# ---------------------------------------------------------------------------
# Urbach model parameters
# ---------------------------------------------------------------------------
# Urbach energy for amorphous chalcogenide films (disorder parameter).
# Literature: 0.05–0.20 eV for phase-change alloys.  Halogens reduce this.
E_U_BASE     = 0.130   # [eV] baseline Urbach energy for amorphous phase
E_U_MIN      = 0.040   # [eV] floor (perfect glass, no passivation can go below)

# Disorder floor for k: represents thin-film contributions independent of
# the Urbach tail (surface roughness Ra ~ λ/50, grain-boundary scattering,
# residual point defects).  Set to 5 % of the intrinsic k_base value.
K_DISORDER_FRAC = 1.5e-4   # was 0.05 (audit M-2): the floor pinned Sb2Se3 k at
# ~2e-3, ~85x above the real <1e-5 at 1550 nm. A good NIR film's residual
# (roughness/grain-boundary) loss is ~1e-5, not 5% of the visible-range k_base.

# ---------------------------------------------------------------------------
# Glass-former network effect (Ge + Sb + Se co-present)
# ---------------------------------------------------------------------------
# Δn EFFECT — sign-corrected 2026-06-03 from literature. Incorporating Ge (or
# Si) into Sb2Se3 LOWERS the amorphous→crystalline index contrast, it does not
# raise it: Ge2Sb2Se5 (GSSe) shows markedly lower Δn than Sb2Se3, and 20% Si
# reduces Δn (Zhang et al. 2019, Nat. Commun. 10:4279; "Incorporating Si into
# Sb2Se3", arXiv:2510.14990). The previous +0.12 "boost" had the WRONG SIGN.
# Net effect for the modest Ge doping in Sb2Se3:Ge:Cl is a small reduction.
GLASS_DELTA_N_BOOST = -0.05   # fractional Δn change from glass network (Ge LOWERS Δn)
# k REDUCTION retained: the rigid, homogeneous Ge-Sb-Se network lowers
# structural disorder (E_U) → lower NIR loss. This direction is supported.
GLASS_K_REDUCTION   = 0.20    # fractional k reduction from network ordering

# ---------------------------------------------------------------------------
# Element database
#   n_cryst    : refractive index in crystalline phase (at 1550 nm)
#   n_amorph   : refractive index in amorphous phase  (at 1550 nm)
#   k_base     : intrinsic extinction coeff. in amorphous phase (at 1550 nm)
#   E_g_amorph : amorphous bandgap [eV] for Urbach calculation
#
# Values informed by:
#   Sb: Delaney et al. 2021, Dong et al. 2019
#   Se: literature trigonal Se and glassy Se
#   Ge: a-Ge and c-Ge at telecom (Ghosh 1998)
#   Te: Petrov et al. (IR properties of Te alloys)
#   S, Bi, In, Sn: chalcogenide glass handbooks (Tanaka 2015)
# ---------------------------------------------------------------------------
ELEMENTS = {
    #       n_cryst  n_amorph  k_base   E_g_amorph [eV]
    "Sb": ( 4.20,    3.10,     0.010,   1.70  ),  # High phase contrast; NIR k_base 0.040->0.010 (audit M-2: 0.040 was a visible-range value; Sb2Se3 is transparent <1e-5 at 1550 nm)
    "Se": ( 2.70,    2.50,     0.002,   2.00  ),  # Low loss, wide gap chalcogenide
    "Ge": ( 4.00,    3.20,     0.008,   1.10  ),  # Glass former; narrows gap slightly
    "Te": ( 4.60,    3.30,     0.250,   0.35  ),  # High n but absorbs at 1550 nm!
    "S":  ( 1.95,    1.75,     0.001,   2.80  ),  # Wide-gap; low index
    "Bi": ( 3.60,    2.70,     0.080,   0.80  ),  # Heavy metal; moderate loss
    "In": ( 3.50,    2.70,     0.080,   0.40  ),  # Semi-metallic; absorbs at 1550nm
    "Sn": ( 3.30,    2.50,     0.150,   0.10  ),  # Near-metallic; high loss
}

# Halogen passivation strengths (relative effectiveness at filling V_Se / V_S)
# Cl is most effective due to size match with Se-vacancy sites.
HALOGENS = {
    "Cl": 0.90,
    "Br": 0.70,
    "F":  0.80,
    "I":  0.50,
}


# ---------------------------------------------------------------------------
# Helper: Clausius-Mossotti mixing
# ---------------------------------------------------------------------------
def _cm_mix(n_values, fracs):
    """
    Clausius-Mossotti effective-medium mixing for a list of (n_i, f_i) pairs.
    Returns n_eff such that:
        (n_eff² - 1)/(n_eff² + 2) = Σ f_i * (n_i² - 1)/(n_i² + 2)

    More accurate than linear mixing because it accounts for local field
    enhancement inside a dielectric medium.
    """
    cm = sum(f * (n**2 - 1.0) / (n**2 + 2.0) for n, f in zip(n_values, fracs))
    cm = min(cm, 0.999)   # prevent n_eff → ∞
    n_eff_sq = (1.0 + 2.0 * cm) / (1.0 - cm)
    return math.sqrt(max(n_eff_sq, 1.0))


# ---------------------------------------------------------------------------
# Helper: Moss Rule
# ---------------------------------------------------------------------------
def _moss_n(E_g):
    """
    n = (95 / E_g)^0.25  [Moss 1950]
    E_g in eV.  Clamp E_g to avoid unphysical divergence for near-zero gaps.
    """
    E_g = max(E_g, 0.10)   # floor at 0.10 eV (metallic-like floor)
    return (95.0 / E_g) ** 0.25


# ---------------------------------------------------------------------------
# Helper: Tauc–Urbach extinction at operating wavelength
# ---------------------------------------------------------------------------
def _urbach_k(k_base, E_g_amorph, E_U):
    """
    k_eff = k_disorder_floor + k_urbach_tail

    Urbach tail:
        k_tail = k_base * exp((E_photon - E_g_amorph) / E_U)

    Below the gap (E_photon < E_g): k_tail is exponentially suppressed.
    Above the gap (E_photon > E_g): k_tail ≥ k_base (full absorption).

    Disorder floor:
        k_floor = K_DISORDER_FRAC * k_base
    Represents thin-film contributions (roughness, grain boundaries)
    that are present regardless of Urbach transparency.
    """
    dE = E_PHOTON_EV - E_g_amorph
    urbach_factor = math.exp(dE / E_U)
    # Clamp: cannot be more absorbing than "fully above-gap" material
    urbach_factor = min(urbach_factor, 5.0)
    k_tail  = k_base * urbach_factor
    k_floor = K_DISORDER_FRAC * k_base
    return k_floor + k_tail


# ---------------------------------------------------------------------------
# Simulator class
# ---------------------------------------------------------------------------
class MorphiumSimulatorPM:
    def __init__(self, seed=None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def simulate(self, state):
        formula = state.get("formula", "Sb2Se3")

        # ----------------------------------------------------------------
        # 1.  Parse formula  (e.g. "Sb2Se3:Ge0.04:Cl0.005")
        #
        #     Supports two syntaxes:
        #       Standard   : Sb2Se3Ge  (stoichiometric integers)
        #       Doped      : Sb2Se3:Ge0.04:Cl0.005 (explicit mole fractions)
        # ----------------------------------------------------------------
        atoms = re.findall(r'([A-Z][a-z]*)(\d*\.?\d*)', formula)

        raw = {}
        for el, amt_str in atoms:
            if not el:
                continue
            amt = float(amt_str) if amt_str else 1.0
            raw[el] = raw.get(el, 0.0) + amt

        if not raw:
            return {"error": "Could not parse formula"}

        total_atoms = sum(raw.values())
        fracs = {el: amt / total_atoms for el, amt in raw.items()}

        # ----------------------------------------------------------------
        # 2.  Separate halogens from matrix elements
        #
        #     Halogens do not contribute to the refractive index (they are
        #     dopants filling anion vacancies) but they modify E_U and k.
        # ----------------------------------------------------------------
        halogen_passiv = 0.0
        for el, strength in HALOGENS.items():
            halogen_passiv += fracs.get(el, 0.0) * strength

        # Matrix elements only (for CM mixing)
        matrix_els   = {el: f for el, f in fracs.items() if el not in HALOGENS}
        matrix_total = sum(matrix_els.values())
        if matrix_total < 1e-9:
            return {"error": "No matrix-forming elements found"}

        matrix_fracs = {el: f / matrix_total for el, f in matrix_els.items()}

        # ----------------------------------------------------------------
        # 3.  Effective Urbach energy after halogen passivation
        #
        #     Each halogen fills vacancy sites, reducing the density of
        #     sub-gap dangling-bond states → narrower Urbach tail.
        #     Passivation saturates: diminishing returns above 30 mol%.
        # ----------------------------------------------------------------
        passiv_sat    = min(halogen_passiv, 0.30) / 0.30   # normalised [0,1]
        E_U_eff       = E_U_BASE * (1.0 - 0.55 * passiv_sat)
        E_U_eff       = max(E_U_eff, E_U_MIN)

        # ----------------------------------------------------------------
        # 4.  Clausius-Mossotti mixing of crystalline and amorphous n
        #
        #     For known elements: use tabulated n_cryst, n_amorph directly.
        #     For unknown elements: fall back to Moss Rule using estimated
        #     bandgap (n_cryst from E_g_amorph*0.6, n_amorph from E_g_amorph).
        # ----------------------------------------------------------------
        n_cryst_vals  = []
        n_amorph_vals = []
        k_base_vals   = []
        Eg_vals       = []
        mf_list       = []

        for el, mf in matrix_fracs.items():
            if el in ELEMENTS:
                nc, na, kb, eg = ELEMENTS[el]
            else:
                # Unknown element: estimate via Moss rule with generic Eg
                eg = 2.0   # generic mid-gap assumption
                nc = _moss_n(eg * 0.60)   # crystalline gap ~ 60% of amorph
                na = _moss_n(eg)
                kb = 0.020
            n_cryst_vals.append(nc)
            n_amorph_vals.append(na)
            k_base_vals.append(kb)
            Eg_vals.append(eg)
            mf_list.append(mf)

        n_cryst_eff  = _cm_mix(n_cryst_vals,  mf_list)
        n_amorph_eff = _cm_mix(n_amorph_vals, mf_list)
        delta_n      = n_cryst_eff - n_amorph_eff
        delta_n      = max(delta_n, 0.0)

        # ----------------------------------------------------------------
        # 5.  Effective loss k in amorphous phase
        #
        #     Volume-fraction weighted average of individual Urbach k values.
        #     Halogens contribute zero to k (they are passivants, not
        #     absorbers in the NIR).
        # ----------------------------------------------------------------
        k_amorph = sum(
            mf * _urbach_k(kb, eg, E_U_eff)
            for mf, kb, eg in zip(mf_list, k_base_vals, Eg_vals)
        )
        # Additional halogen-mediated reduction in k (passivated defects
        # no longer contribute disorder floor absorption).
        halogen_k_suppress = 1.0 - 0.40 * passiv_sat   # up to 40% reduction
        k_amorph *= halogen_k_suppress

        k_amorph = max(k_amorph, 1e-6)   # absolute floor (numerical)

        # ----------------------------------------------------------------
        # 6.  Glass-former network effect (Ge + Sb + Se co-present)
        #
        #     Physical origin: tetrahedral Ge anchors connect pyramidal Sb
        #     units through Se bridges, producing a rigid, homogeneous glass.
        #       • Δn: Ge/Si incorporation LOWERS the index contrast (GSSe <
        #         Sb2Se3; Si:Sb2Se3 < Sb2Se3) — sign-corrected, see the
        #         GLASS_DELTA_N_BOOST constant above.
        #       • Less structural fluctuation in amorph → lower E_U → lower k
        # ----------------------------------------------------------------
        has_Ge = fracs.get("Ge", 0.0) > 0.01
        has_Sb = fracs.get("Sb", 0.0) > 0.01
        has_Se = fracs.get("Se", 0.0) > 0.01

        if has_Ge and has_Sb and has_Se:
            delta_n  *= (1.0 + GLASS_DELTA_N_BOOST)
            k_amorph *= (1.0 - GLASS_K_REDUCTION)
            k_amorph  = max(k_amorph, 1e-6)

        # ----------------------------------------------------------------
        # 7.  Seed-controlled deterministic noise (thin-film variability)
        #
        #     Represents real deposition-to-deposition variation:
        #     stoichiometry ±1%, film thickness ±2 nm, roughness Ra.
        # ----------------------------------------------------------------
        if self.seed is not None:
            noise_dn = 1.0 + random.uniform(-0.03, 0.03)   # ±3% Δn
            noise_k  = 1.0 + random.uniform(-0.15, 0.15)   # ±15% k (more sensitive)
        else:
            noise_dn = 1.0
            noise_k  = 1.0

        delta_n  *= noise_dn
        k_amorph *= noise_k
        k_amorph  = max(k_amorph, 1e-6)

        # ----------------------------------------------------------------
        # 8.  Figure of merit
        # ----------------------------------------------------------------
        fom = delta_n / k_amorph

        return {
            "delta_n":           round(delta_n,  4),
            "loss_k":            round(k_amorph, 6),
            "fom":               round(fom,      2),
            # Diagnostic outputs (useful for GA debugging, not in contract)
            "_n_cryst_eff":      round(n_cryst_eff,  4),
            "_n_amorph_eff":     round(n_amorph_eff, 4),
            "_E_U_eff_eV":       round(E_U_eff,      4),
            "_halogen_passiv":   round(halogen_passiv, 4),
            "_glass_bonus":      has_Ge and has_Sb and has_Se,
            "seed":              self.seed,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def execute(state):
    seed    = state.get("seed", 42)
    sim     = MorphiumSimulatorPM(seed=seed)
    metrics = sim.simulate(state)
    result  = {
        "state":             state,
        "metrics":           metrics,
        "sim_model_version": SIM_MODEL_VERSION,
        "hash":              hashlib.sha256(
            json.dumps(metrics, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }
    return result


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    tests = [
        ("Sb2Se3",             401, "Base champion (no dopants)"),
        ("Sb2Se3:Ge:Cl",       401, "Original GOLDEN_IMAGE champion"),
        ("Sb2Se3:Ge0.1:Cl0.05",401, "Heavier Ge + Cl doping"),
        ("Sb2Se3Te",           401, "Te addition (should penalise FOM)"),
        ("Ge2Sb2Te5",          401, "GST — classic phase-change, absorbs at 1550nm"),
        ("Sb2S3",              401, "Sb2S3 — low loss, lower Δn"),
    ]

    print("=== Morphium-PM Tier 1.5 — Formula Sweep at λ=1550 nm ===")
    print(f"{'Formula':30s}  {'Δn':>8}  {'k':>10}  {'FOM':>8}  {'n_cryst':>8}  {'E_U':>6}")
    print("-" * 80)
    for formula, seed, desc in tests:
        r = execute({"formula": formula, "seed": seed})["metrics"]
        glass = "✓" if r.get("_glass_bonus") else " "
        print(f"  {formula:28s}  "
              f"{r['delta_n']:8.4f}  "
              f"{r['loss_k']:10.6f}  "
              f"{r['fom']:8.1f}  "
              f"{r['_n_cryst_eff']:8.4f}  "
              f"{r['_E_U_eff_eV']:6.4f}  {glass}")
        if desc:
            print(f"    ({desc})")

    print()
    print("=== Halogen passivation effect on Sb2Se3:Ge ===")
    print(f"{'Halogen frac':15s}  {'E_U':>6}  {'k':>10}  {'FOM':>8}")
    for cl_frac in [0.0, 0.01, 0.03, 0.05, 0.10, 0.20]:
        formula = f"Sb2Se3:Ge:{f'Cl{cl_frac}' if cl_frac > 0 else 'X0'}"
        if cl_frac == 0.0:
            formula = "Sb2Se3:Ge"
        r = execute({"formula": formula, "seed": 401})["metrics"]
        print(f"  Cl={cl_frac:.2f}           "
              f"  {r['_E_U_eff_eV']:6.4f}"
              f"  {r['loss_k']:10.6f}"
              f"  {r['fom']:8.1f}")
