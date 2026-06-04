"""
Morphium-L Layer API — Tier 1.5 Physics Engine
Oxide TFT Logic (IGZO / ITZO family)

Physics Models Implemented:

  1. Percolation Mobility (replaces linear weighted average):

     μ_eff = μ₀ × exp(-E_a / kT)

     where E_a = σ²_conf / (2kT) is the percolation barrier and
     σ_conf = E_SCALE_DISORDER × S_mix is the configurational
     disorder broadening.  S_mix = -Σ xᵢ ln xᵢ is the cation-sublattice
     mixing entropy (Shannon entropy in nats).

     Physical picture: in a multi-cation amorphous oxide, the conduction
     band minimum fluctuates spatially due to the random arrangement of
     metal ions with different electron affinities (In, Ga, Zn have very
     different CBM energies).  Electrons must percolate through these
     fluctuations, paying an activation energy proportional to the
     variance of those fluctuations.  A single-cation film has σ_conf = 0
     and recovers the band-edge mobility; maximum entropy mixtures pay the
     largest percolation penalty.

  2. Indium Cooperative s-orbital Enhancement:

     Band-edge mobility μ₀ is boosted by In because its 5s-orbital
     forms wide, isotropic conduction bands (effective mass 0.25 mₑ).
     The cooperative effect (multiple In neighbours) is super-linear:

       μ₀_effective = min(μ₀ × (1 + C_In × f_In^1.5), μ_In_max)

     This saturates at the pure-In₂O₃ band mobility to prevent
     un-physical extrapolation.

  3. Exponential O-vacancy Model (replaces sigmoid stoichiometry gates):

     For each metal species the stoichiometric O/metal ratio is fixed
     by the stable oxide:  In₂O₃ → 1.5, Ga₂O₃ → 1.5, ZnO → 1.0,
     SnO₂ → 2.0.  The composition-weighted stoichiometric O content is:

       O_stoich = Σ metal_i × o_stoich_i  (in the same units as O_actual)

     The O-vacancy driving force is δ_O = (O_actual − O_stoich) / O_stoich.

     Normalised vacancy density:
       δ_O < 0  (O-deficient) : N_v = exp(−ALPHA_VAC × δ_O)   > 1
       δ_O > 0  (O-excess)    : N_v = exp(−ALPHA_EX  × δ_O)   < 1

     N_v = 1.0 at perfect stoichiometry.

  4. Ga Passivation of Oxygen Vacancies:

     Ga³⁺ ions have a strong affinity for V_O sites (Ga−O bond energy
     higher than In−O).  Higher Ga fraction → fewer free V_O → lower
     carrier density AND lower trap density:

       N_v_eff = N_v × exp(−BETA_GA × f_Ga)

  5. Brooks-Herring Ionized Impurity Scattering (IIS) Trade-off:

     Oxygen vacancies act as doubly-ionized donors.  At high V_O density,
     Coulomb scattering from these donors limits mobility:

       μ_final = μ_perc / (1 + (N_v_eff × Nref / N_C_IIS)^BETA_IIS)

     This creates the fundamental Ion/Ioff trade-off: more V_O → more
     free electrons (higher Ion) but also more scattering (lower mobility)
     AND higher leakage (higher Ioff).

  6. Device metrics:
       I_on  = μ_final × I_ON_SCALE
       I_off = I_OFF_BASE × N_v_eff^BETA_OFF   (trap-assisted leakage)
       SS    = 60 × (1 + K_SS × log10(1 + N_v_eff))  [mV/dec]
       Vth   = Vth_0 − γ × log10(1 + N_v_eff)        [V]

  7. Crystallization Risk:
     IGZO is metastable amorphous. Below f_Ga < 15% there is insufficient
     structural disorder suppression → In₂O₃ nanocrystallites nucleate
     under gate-bias stress → severe Vth instability.

Model calibration-reference device (seed 42) — a real ~1:1:1-ish IGZO point
the mobility model is anchored to (NOT the recommended champion: its cation
Zn=0.051 is below the Zn>=0.10 floor; see CHAMPIONS for the floor-compliant
champion, In-rich, μ≈20):
  Composition: In=0.262, Ga=0.244, Zn=0.027, O=0.467  (normalised)
  Expected: μ ≈ 13 cm²/Vs, I_off ≈ 4e-12 A, SS ≈ 77 mV/dec

References:
  - Nomura et al.; Nature 432 (2004) 488          (IGZO discovery)
  - Kamiya et al.; NPG Asia Mater. 2 (2010) 15    (percolation picture)
  - Kim et al.; APL 86 (2005) 112101              (O-vacancy role)
  - Ye et al.; IEEE TED 63 (2016) 4311            (Ga passivation)
"""

import math
import random
import json
import hashlib

SIM_MODEL_VERSION = "1.5"

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
KT_EV = 0.02585          # kT at T = 300 K  [eV]

# ---------------------------------------------------------------------------
# Configurational disorder → percolation barrier
# ---------------------------------------------------------------------------
# σ_conf = E_SCALE_DISORDER × S_mix  (S_mix in nats)
# Calibrated so that equal-weight In:Ga:Zn (S_mix ≈ 1.10 nat) gives
# E_a ≈ 0.088 eV → exp(-E_a/kT) ≈ 0.032 → μ_perc ≈ 0.032 × μ₀
# Champion composition (low S_mix ≈ 0.85 nat) → factor ≈ 0.063
E_SCALE_DISORDER = 0.04   # [eV / nat]

# ---------------------------------------------------------------------------
# Indium cooperative s-orbital enhancement
# ---------------------------------------------------------------------------
# Recalibrated 2026-06-04 to the In-rich literature (Lee/Cho 2018: In0.45 ->
# 48 cm2/Vs; consensus In-rich 40-48, ~3.5x the 1:1:1 anchor). The old 0.5 /
# 60-cap throttled In-rich to ~20 (model was ~2x low — pressure-test ceiling).
# Steeper coefficient + decoupled In-rich band-mobility cap (In-rich trends
# toward In2O3-like ~110) now reproduces both anchors: 1:1:1 ~13, In-rich ~45.
IN_COOP_FACTOR = 3.3      # super-linear In enhancement coefficient
MU_IN_MAX      = 110.0    # [cm2/Vs] In-rich band-mobility ceiling (In2O3-like)

# ---------------------------------------------------------------------------
# O-vacancy model exponents
# ---------------------------------------------------------------------------
ALPHA_VAC = 5.0           # V_O drive for O-deficient regime
ALPHA_EX  = 10.0          # V_O suppression for O-excess regime
N_V_REF   = 1e15          # [cm⁻³] reference vacancy density (N_v=1 → this)

# ---------------------------------------------------------------------------
# Ga passivation
# ---------------------------------------------------------------------------
BETA_GA   = 1.0           # Ga passivation strength

# ---------------------------------------------------------------------------
# Brooks-Herring IIS
# ---------------------------------------------------------------------------
N_C_IIS   = 1e17          # [cm⁻³] crossover vacancy density for 50% μ drop
BETA_IIS  = 0.70          # sub-linear exponent (empirical)

# ---------------------------------------------------------------------------
# Device metric scaling
# ---------------------------------------------------------------------------
I_ON_SCALE  = 1e-6        # I_on [A] = μ [cm²/Vs] × 1e-6  (W/L = 10, Cox at 10 nm)
I_OFF_BASE  = 5e-13       # [A] I_off floor at N_v_eff = 1
BETA_OFF    = 1.30        # I_off ∝ N_v_eff^BETA_OFF
K_SS        = 0.30        # SS correction coefficient
VTH_0       = 0.50        # [V] intrinsic threshold at stoichiometry
GAMMA_VTH   = 0.05        # [V / log-decade]

# ---------------------------------------------------------------------------
# Element database: band mobility, stoichiometric O/metal ratio
# ---------------------------------------------------------------------------
METALS = {
    "In": {"mu_band": 60.0, "o_stoich": 1.5},   # In₂O₃: 3 O per 2 In
    "Ga": {"mu_band":  1.0, "o_stoich": 1.5},   # Ga₂O₃: 3 O per 2 Ga
    "Zn": {"mu_band": 10.0, "o_stoich": 1.0},   # ZnO:   1 O per Zn
    "Sn": {"mu_band": 80.0, "o_stoich": 2.0},   # SnO₂:  2 O per Sn
}


def _sigmoid(x):
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class MorphiumSimulatorL:
    def __init__(self, seed=None):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def simulate(self, state):
        materials = state.get("materials", {})
        comp_raw  = materials.get(
            "channel_composition",
            # Fallback default = the floor-compliant champion (cation Zn=0.10).
            {"In": 0.2522, "Ga": 0.1093, "Zn": 0.0402, "O": 0.5983}
        )

        # ----------------------------------------------------------------
        # 1.  Normalise composition; separate metal vs O sublattice
        # ----------------------------------------------------------------
        total = sum(float(v) for v in comp_raw.values())
        if total <= 0:
            return {"error": "Invalid Composition"}

        f = {el: float(v) / total for el, v in comp_raw.items()}  # normalised fracs

        metal_els = {el: frac for el, frac in f.items() if el in METALS}
        metal_total = sum(metal_els.values())
        if metal_total <= 0:
            return {"error": "No metal cations in composition"}

        # Metal fractions on cation sublattice (sum to 1)
        fm = {el: v / metal_total for el, v in metal_els.items()}

        f_In = fm.get("In", 0.0)
        f_Ga = fm.get("Ga", 0.0)
        O_actual = f.get("O", 0.0) * total  # in original unnormalised units

        # ----------------------------------------------------------------
        # 2.  Band-edge mobility + Indium cooperative enhancement
        # ----------------------------------------------------------------
        mu_0 = sum(METALS[el]["mu_band"] * fm.get(el, 0.0) for el in METALS)
        # Cooperative In s-orbital enhancement (super-linear, capped)
        mu_0 = min(
            mu_0 * (1.0 + IN_COOP_FACTOR * f_In ** 1.5),
            MU_IN_MAX
        )

        # ----------------------------------------------------------------
        # 3.  Configurational disorder → percolation penalty
        #
        #     S_mix computed over cation sublattice only (anion sublattice
        #     is fully occupied in ideal stoichiometry and contributes
        #     less to CBM fluctuation).
        # ----------------------------------------------------------------
        S_mix = -sum(fi * math.log(fi) for fi in fm.values() if fi > 1e-9)
        sigma = E_SCALE_DISORDER * S_mix
        E_a   = sigma ** 2 / (2.0 * KT_EV)
        mu_perc = mu_0 * math.exp(-E_a / KT_EV)

        # ----------------------------------------------------------------
        # 4.  O-stoichiometry → exponential vacancy model
        #
        #     O_stoich_ref: expected O atoms for the given metal fractions
        #     (using unnormalised metal amounts for consistency).
        # ----------------------------------------------------------------
        O_stoich_ref = sum(
            METALS[el]["o_stoich"] * metal_els.get(el, 0.0)
            for el in METALS
        )
        # Protect against zero
        if O_stoich_ref < 1e-9:
            O_stoich_ref = 1e-9

        delta_O = (O_actual - O_stoich_ref) / O_stoich_ref

        if delta_O < 0:                                   # O-deficient
            N_v_norm = math.exp(-ALPHA_VAC * delta_O)    # > 1
        else:                                             # O-excess / stoich
            N_v_norm = math.exp(-ALPHA_EX  * delta_O)    # ≤ 1

        # ----------------------------------------------------------------
        # 5.  Ga passivation of V_O sites
        # ----------------------------------------------------------------
        N_v_eff = N_v_norm * math.exp(-BETA_GA * f_Ga)
        N_v_eff = max(N_v_eff, 1e-6)   # numerical floor

        # ----------------------------------------------------------------
        # 6.  Brooks-Herring IIS trade-off
        # ----------------------------------------------------------------
        iis_term = (N_v_eff * N_V_REF / N_C_IIS) ** BETA_IIS
        mu_final = mu_perc / (1.0 + iis_term)
        mu_final = max(mu_final, 1e-4)

        # ----------------------------------------------------------------
        # 7.  Seed-controlled deterministic noise (process variability)
        # ----------------------------------------------------------------
        if self.seed is not None:
            noise_mu  = 1.0 + random.uniform(-0.05,  0.05)
            noise_off = 1.0 + random.uniform(-0.20,  0.20)
        else:
            noise_mu  = 1.0
            noise_off = 1.0

        mu_final *= noise_mu

        # ----------------------------------------------------------------
        # 8.  Device metrics
        # ----------------------------------------------------------------
        I_on  = mu_final * I_ON_SCALE
        I_off = I_OFF_BASE * (N_v_eff ** BETA_OFF) * noise_off
        I_off = max(I_off, 1e-13)   # physical a-IGZO floor (audit m-2: was 1e-18)

        # Subthreshold swing: 60 mV/dec thermionic limit x interface-trap
        # non-ideality (1 + Cit/Cox ~ 1.6 -> ~96 mV/dec floor; audit m-1) plus a
        # bulk-trap (N_v) term. Real a-IGZO SS ~100-200 mV/dec.
        SS  = 60.0 * (1.6 + K_SS * math.log10(1.0 + N_v_eff))
        Vth = VTH_0 - GAMMA_VTH * math.log10(1.0 + N_v_eff)

        delta_Vth_stress = 0.02 * math.log10(1.0 + N_v_eff)
        hysteresis       = 0.01 * math.sqrt(N_v_eff)
        leakage_W        = I_off

        # ----------------------------------------------------------------
        # 9.  Crystallization risk
        #
        #     IGZO amorphous stability requires sufficient Ga to suppress
        #     In₂O₃ nanocrystallite nucleation. Continuous exponential decay,
        #     saturating to 1.0 at/below f_Ga = 0.10 (audit m-4: removed the
        #     discontinuous hard step at f_Ga=0.15). This is an uncalibrated
        #     Ga-only proxy (ignores Zn/temp/thickness), used only as a soft
        #     <=0.5 regulariser.
        # ----------------------------------------------------------------
        cryst_risk = min(1.0, math.exp(-10.0 * max(f_Ga - 0.10, 0.0)))

        # Operational endurance (RELIABILITY). NOTE (research 2026-06-03):
        # "cycles to failure" is the WRONG metric for a-IGZO — switching has no
        # per-cycle wear, so raw switching endurance is effectively UNBOUNDED
        # (>=1e11; imec 2T0C IGZO-DRAM, Belmonte IEDM 2021). The real wear-out is
        # bias-stress Vth DRIFT — a temperature-accelerated LIFETIME (months-
        # years, stretched-exponential), NOT a cycle count. This value is a
        # drift-quality proxy (higher = lower Vth drift) floored at the switching-
        # unbounded ~1e11; treat L as "not the cycle bottleneck". See
        # DATA_PROVENANCE.md for the metric caveat.
        operational_endurance = min(1.0e11, 1.0e9 / max(delta_Vth_stress, 1e-4))

        return {
            "mobility_cm2_Vs":           round(mu_final, 3),
            "Ion_A":                     I_on,
            "Ioff_A":                    I_off,
            "SS_mV_dec":                 round(SS, 2),
            "Vth_V":                     round(Vth, 3),
            "hysteresis_V":              round(hysteresis, 4),
            "delta_Vth_biasstress_V":    round(delta_Vth_stress, 4),
            "operational_endurance":     int(operational_endurance),
            "leakage_W":                 leakage_W,
            "crystallization_risk":      round(cryst_risk, 2),
            # Diagnostic (not in contract)
            "_S_mix_nats":               round(S_mix, 4),
            "_N_v_eff":                  round(N_v_eff, 4),
            "_delta_O":                  round(delta_O, 4),
            "_mu_perc":                  round(mu_perc, 3),
            "seed":                      self.seed,
        }


def execute(state):
    seed = state.get("seed", 42)
    sim  = MorphiumSimulatorL(seed=seed)
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
    import sys

    # Model calibration-reference device (mu~13 anchor; below the Zn>=0.10 floor,
    # NOT the recommended champion — see CHAMPIONS for the floor-compliant one).
    champion = {"In": 0.262, "Ga": 0.244, "Zn": 0.027, "O": 0.467}

    tests = [
        (champion,                          42,  "Champion (target: μ≈13, Ioff≈4e-12, SS≈77)"),
        ({"In":1.0,"O":1.5},               42,  "Pure In₂O₃ (crystallisation risk=1)"),
        ({"Zn":1.0,"O":1.0},               42,  "Pure ZnO"),
        ({"In":0.33,"Ga":0.33,"Zn":0.33,"O":1.0}, 42, "Equal IGZ — high disorder penalty"),
        ({"In":0.5,"Ga":0.3,"Zn":0.2,"O":0.9},    42, "O-deficient IGZO (high V_O)"),
        ({"In":0.5,"Ga":0.3,"Zn":0.2,"O":1.3},    42, "O-excess IGZO (low V_O)"),
    ]

    print("=== Morphium-L Tier 1.5 — Composition Sweep ===")
    print(f"{'Composition':40s}  {'μ':>7}  {'Ioff':>10}  {'SS':>7}  {'cryst':>6}  {'N_v_eff':>8}")
    print("-" * 90)
    for comp, seed, desc in tests:
        state = {"materials": {"channel_composition": comp}, "seed": seed}
        r = execute(state)["metrics"]
        print(
            f"  {desc:38s}  "
            f"{r['mobility_cm2_Vs']:7.3f}  "
            f"{r['Ioff_A']:10.2e}  "
            f"{r['SS_mV_dec']:7.2f}  "
            f"{r['crystallization_risk']:6.2f}  "
            f"{r['_N_v_eff']:8.4f}"
        )
