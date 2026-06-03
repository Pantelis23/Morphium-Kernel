"""
Loop Kernel Adapter
Runs high-throughput search against the Morphium Kernel.
Uses Evolutionary Optimization (Genetic Algorithm) to find candidates.

Supported layers: L, PM, E, EM, M

Fixes vs v1.0:
  - Correct import path (src.morphium_kernel.kernel)
  - PM, E and EM layer support (generators + mutators)
  - Layer L: hard constraint f_Ga >= 0.20 (amorphous stability requirement)
  - GA-adjusted score: process-robustness margin bonuses (v2)
  - Tournament selection (better than random parent selection)
  - Ion_Ioff computed inline (contract metric, not returned by api directly)
  - PM: seeded near reference champion Sb2Se3:Ge:Cl; always includes Cl

v2 robustness improvements (all layers):
  - L: cryst_risk penalty tightened (0.5 → 0.3), Ga_cation floor raised to 0.20
  - PM: delta_n margin bonus (+500 per unit above 0.35); heavy penalty below 0.30
  - E: anneal capped at 560°C (away from agglomeration edge >580°C)
  - EM: x_Sc capped at 0.38 (safe side of secondary phase boundary)
"""
import sys
import os
import argparse
import random
import json
import re
from pathlib import Path

# Add project root to path (script lives in tools/, project root is one level up)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# Also put tools/ on the path so we can reuse the Monte-Carlo yield model.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.morphium_kernel.kernel import KernelClient

# Robust (yield-gated) objective reuses the process-sigma Monte-Carlo yield model
# already implemented in sensitivity_analysis.py. Imported here so the search can
# optimise for *fabrication yield* directly instead of peak nominal metrics.
try:
    from sensitivity_analysis import run_monte_carlo as _mc_yield
except Exception:  # pragma: no cover - peak mode must work even if this fails
    _mc_yield = None


# ---------------------------------------------------------------------------
# GA-adjusted scoring (augments kernel score with GA-specific constraints)
# ---------------------------------------------------------------------------

def ga_score(kc, layer, metrics):
    """Kernel contract score + GA-level constraints + process robustness margins."""
    s = kc.score(layer, metrics)

    if layer == "L":
        # Ion_Ioff computed inline (contract metric, not returned by api)
        i_on  = metrics.get("Ion_A", 0)
        i_off = metrics.get("Ioff_A", 1e-3)
        if i_off > 0:
            ion_ioff = i_on / max(i_off, 1e-18)
            s += min(ion_ioff, 1e10) * 2.5e-9   # rescale to ~same range as mobility score

        # Robustness: penalise high crystallization risk more aggressively
        # Tightened from 0.5 → 0.3 so GA stays well away from the instability cliff
        cryst = metrics.get("crystallization_risk", 1.0)
        if cryst > 0.3:
            s -= 200.0 * cryst

    elif layer == "PM":
        # Robustness: reward delta_n margin above the 0.30 threshold.
        # Without this the GA parks at delta_n=0.301 which gives <40% MC yield.
        # Target: delta_n >= 0.40 for ~90% MC yield at +/-3% Se/Sb sigma.
        dn = metrics.get("delta_n", 0.0)
        if dn >= 0.35:
            s += (dn - 0.35) * 500.0   # bonus: reward extra margin
        elif dn < 0.30:
            s -= (0.30 - dn) * 5000.0  # heavy penalty: failing the hard threshold

    return s


# ---------------------------------------------------------------------------
# State Generators
# ---------------------------------------------------------------------------

def _ga_min_ga_fraction():
    """Minimum Ga cation fraction for amorphous stability."""
    return random.uniform(0.15, 0.45)


def generate_random_state_L():
    """Random IGZO composition with amorphous stability constraint (Ga >= 20%)."""
    # Sample metal fractions with guaranteed Ga >= 20% (raised from 15% for robustness)
    f_Ga = random.uniform(0.20, 0.50)
    f_In = random.uniform(0.10, 0.80 - f_Ga)
    f_Zn = max(0.01, random.uniform(0.0, 0.30))
    metal_total = f_In + f_Ga + f_Zn

    # O: near stoichiometry (In₂O₃: 1.5, Ga₂O₃: 1.5, ZnO: 1.0 O/metal)
    fm_In = f_In / metal_total
    fm_Ga = f_Ga / metal_total
    fm_Zn = f_Zn / metal_total
    o_stoich = fm_In * 1.5 + fm_Ga * 1.5 + fm_Zn * 1.0
    # Vary O/metal ratio ±20% from stoichiometry
    o_ratio = o_stoich * random.uniform(0.80, 1.20)
    f_O = o_ratio * metal_total

    total = metal_total + f_O
    return {
        "materials": {
            "channel_material": "IGZO",
            "channel_composition": {
                "In": round(f_In / total, 4),
                "Ga": round(f_Ga / total, 4),
                "Zn": round(f_Zn / total, 4),
                "O":  round(f_O  / total, 4),
            }
        }
    }


def generate_random_state_PM():
    """
    Random chalcogenide formula seeded near the reference champion Sb2Se3:Ge:Cl.

    Jacobian at reference:
      ∂FOM/∂Cl = +262  → more Cl always helps (up to passivation saturation ~30%)
      ∂FOM/∂Ge = +58.3 → more Ge helps (glass-former network)
      ∂FOM/∂Sb = -126  → less Sb per unit helps (dilution of Ge/Cl ratio)
      ∂FOM/∂Se = -22.9 → slightly less Se per unit helps

    Exploration strategy:
      - Start near Sb2Se3 ratio (Sb:Se ≈ 1:1.5 by unit cell)
      - Cl always included (0.02-0.15 range, up from 0-0.10)
      - Ge always included (0.05-0.40 range)
      - Occasionally try Se-rich or Sb-lean variants
    """
    # Seeded near reference: Sb2Se3 base
    sb = round(random.uniform(1.2, 2.5), 2)
    se = round(random.uniform(2.5, 4.5), 2)
    # Ge and Cl: always include (Jacobian says they always help)
    ge = round(random.uniform(0.05, 0.40), 3)
    cl = round(random.uniform(0.02, 0.15), 4)

    parts = [f"Sb{sb}", f"Se{se}", f"Ge{ge}", f"Cl{cl}"]
    return {"formula": ":".join(parts)}


def generate_random_state_E():
    """Random HZO composition with optional Al/Si stabilisers."""
    x_Zr = round(random.uniform(0.25, 0.75), 3)
    x_Hf = round(1.0 - x_Zr, 3)

    # Optional Al doping (optimal < 6%)
    if random.random() < 0.4:
        x_Al = round(random.uniform(0.01, 0.06), 3)
        total = x_Hf + x_Zr + x_Al
        formula = f"Hf{round(x_Hf/total,3)}Zr{round(x_Zr/total,3)}Al{round(x_Al/total,3)}O2"
    else:
        formula = f"Hf{x_Hf}Zr{x_Zr}O2"

    thickness = round(random.uniform(5.0, 15.0), 1)
    # Cap anneal at 560°C — above this agglomeration risk rises sharply.
    # Model shows Pr still ~18 µC/cm² at 540°C; 583°C champion has <5°C furnace margin.
    anneal    = round(random.uniform(350.0, 560.0), 0)

    return {"formula": formula, "thickness_nm": thickness, "anneal_temp_C": anneal}


def generate_random_state_EM():
    """Random ScAlN formula in safe wurtzite region (x_Sc <= 0.38).

    Pareto analysis shows x_Sc=0.38 gives d33=16.4 pC/N with sec_phase_risk=0.47.
    At x_Sc=0.42 (previous champion) sec_phase_risk=0.814 → ~30-45% real yield.
    Capping at 0.38 raises expected real yield to ~65-75%.
    """
    x_Sc = round(random.uniform(0.15, 0.38), 3)
    x_Al = round(1.0 - x_Sc, 3)
    substrate = random.choice(["Si", "SiC", "Al2O3"])
    dep_temp = round(random.uniform(250.0, 500.0), 0)
    return {
        "formula": f"Sc{x_Sc}Al{x_Al}N",
        "substrate": substrate,
        "dep_temp_C": dep_temp,
    }


GENERATORS = {
    "L":  generate_random_state_L,
    "PM": generate_random_state_PM,
    "E":  generate_random_state_E,
    "EM": generate_random_state_EM,
}


# ---------------------------------------------------------------------------
# Mutators
# ---------------------------------------------------------------------------

def mutate_L(state, step=0.08):
    """Mutate IGZO composition. Enforces f_Ga >= 0.15 on cation sublattice."""
    new_state = json.loads(json.dumps(state))
    comp = new_state["materials"]["channel_composition"]

    # Pick an element to nudge
    el = random.choice(list(comp.keys()))
    delta = random.gauss(0, step)
    comp[el] = max(comp[el] + delta, 0.001)

    # Re-normalize
    total = sum(comp.values())
    for k in comp:
        comp[k] /= total

    # Enforce amorphous stability: Ga >= 15% on cation sublattice
    metals = {k: v for k, v in comp.items() if k != "O"}
    metal_total = sum(metals.values())
    f_Ga_cation = comp.get("Ga", 0) / metal_total if metal_total > 0 else 0

    if f_Ga_cation < 0.20:
        deficit = 0.20 * metal_total - comp.get("Ga", 0)
        comp["Ga"] = comp.get("Ga", 0) + deficit
        # Re-normalize O is fixed, re-normalize metals
        metals = {k: comp[k] for k in comp if k != "O"}
        metal_sum = sum(metals.values())
        o_val = comp["O"]
        total2 = metal_sum + o_val
        for k in comp:
            comp[k] /= total2

    return new_state


def mutate_PM(state, step=0.05):
    """Mutate chalcogenide formula by perturbing stoichiometric coefficients."""
    new_state = json.loads(json.dumps(state))
    formula = new_state.get("formula", "Sb2Se3")

    atoms = re.findall(r'([A-Z][a-z]*)(\d*\.?\d*)', formula)
    raw = {}
    for el, amt_str in atoms:
        if el:
            amt = float(amt_str) if amt_str else 1.0
            raw[el] = raw.get(el, 0.0) + amt

    # Randomly mutate one element's coefficient
    el = random.choice(list(raw.keys()))
    raw[el] = max(raw[el] * (1.0 + random.gauss(0, step)), 0.001)

    # Occasionally add/remove Cl or Ge dopants
    if random.random() < 0.15:
        if "Cl" not in raw:
            raw["Cl"] = round(random.uniform(0.001, 0.05), 4)
        else:
            raw.pop("Cl")
    if random.random() < 0.10:
        if "Ge" not in raw:
            raw["Ge"] = round(random.uniform(0.05, 0.25), 3)

    parts = [f"{e}{round(v, 4)}" if round(v, 4) != 1.0 else e
             for e, v in raw.items() if v > 0]
    new_state["formula"] = ":".join(parts)
    return new_state


def mutate_E(state, step=0.05):
    """Mutate HZO formula (Zr fraction, thickness, annealing temperature)."""
    new_state = json.loads(json.dumps(state))
    formula = new_state.get("formula", "Hf0.5Zr0.5O2")

    # Extract Zr fraction
    m = re.search(r'Zr(\d*\.?\d+)', formula)
    x_Zr = float(m.group(1)) if m else 0.5

    choice = random.randint(0, 2)
    if choice == 0:
        x_Zr_new = min(max(x_Zr + random.gauss(0, step), 0.05), 0.95)
        x_Hf_new = round(1.0 - x_Zr_new, 3)
        new_state["formula"] = f"Hf{x_Hf_new}Zr{round(x_Zr_new, 3)}O2"
    elif choice == 1:
        t = new_state.get("thickness_nm", 10.0)
        new_state["thickness_nm"] = round(min(max(t + random.gauss(0, 2.0), 4.0), 25.0), 1)
    else:
        T = new_state.get("anneal_temp_C", 450.0)
        new_state["anneal_temp_C"] = round(min(max(T + random.gauss(0, 30.0), 350.0), 560.0), 0)

    return new_state


def mutate_EM(state, step=0.02):
    """Mutate ScAlN: Sc fraction, substrate, or deposition temperature."""
    new_state = json.loads(json.dumps(state))
    formula = new_state.get("formula", "Sc0.4Al0.6N")
    m = re.search(r'Sc(\d*\.?\d+)', formula)
    x_Sc = float(m.group(1)) if m else 0.35

    choice = random.randint(0, 2)
    if choice == 0:
        # Nudge Sc fraction (stay below cliff)
        x_Sc_new = min(max(x_Sc + random.gauss(0, step), 0.10), 0.38)
        x_Al_new = round(1.0 - x_Sc_new, 3)
        new_state["formula"] = f"Sc{round(x_Sc_new, 3)}Al{x_Al_new}N"
    elif choice == 1:
        # Change substrate
        new_state["substrate"] = random.choice(["Si", "SiC", "Al2O3"])
    else:
        # Adjust deposition temperature
        T = new_state.get("dep_temp_C", 350.0)
        new_state["dep_temp_C"] = round(min(max(T + random.gauss(0, 40.0), 200.0), 550.0), 0)

    return new_state


MUTATORS = {
    "L":  mutate_L,
    "PM": mutate_PM,
    "E":  mutate_E,
    "EM": mutate_EM,
}


# ---------------------------------------------------------------------------
# Tournament selection
# ---------------------------------------------------------------------------

def tournament_select(population_with_scores, k=3):
    """Select best candidate from k random entrants."""
    entrants = random.sample(population_with_scores, min(k, len(population_with_scores)))
    return max(entrants, key=lambda x: x[1])[0]


# ---------------------------------------------------------------------------
# Main search loop
# ---------------------------------------------------------------------------

def run_search(layer, budget, kc, pop_size=30, step_start=0.12, step_end=0.02,
               robust=False, mc_samples=64):
    if layer not in GENERATORS:
        supported = ", ".join(GENERATORS.keys())
        print(f"Error: Layer {layer!r} not supported. Supported: {supported}")
        return
    if robust and _mc_yield is None:
        print("Error: --robust requested but sensitivity_analysis.run_monte_carlo "
              "could not be imported.")
        return

    obj = f"ROBUST (fab-yield, {mc_samples} MC/candidate)" if robust else "PEAK (nominal metric)"
    print(f"\nStarting GA Search: Layer={layer}, Budget={budget}, Pop={pop_size}")
    print(f"Objective: {obj}")
    print(f"{'─'*60}")

    contract = kc.contract(layer)
    generator = GENERATORS[layer]
    mutator   = MUTATORS[layer]

    # Initial population
    population = [(generator(), None) for _ in range(pop_size)]

    best_score  = -float("inf")
    best_state  = None
    best_trial  = 0
    best_yield  = None
    n_promoted  = 0

    for i in range(budget):
        # Annealing step size: starts large (exploration), shrinks (exploitation)
        progress  = i / max(budget - 1, 1)
        step_size = step_start + (step_end - step_start) * progress

        # Select candidate
        if i < pop_size:
            # Burn in: evaluate initial population first
            candidate_state = population[i][0]
        else:
            # Tournament selection from evaluated population
            evaluated = [(s, sc) for s, sc in population if sc is not None]
            if not evaluated:
                evaluated = [(s, 0.0) for s, _ in population]
            parent = tournament_select(evaluated)
            candidate_state = mutator(parent, step=step_size)

        # Simulate
        seed = i + 100
        result  = kc.simulate(layer, candidate_state, seed=seed)
        metrics = result.get("metrics", result.get("data", {}))

        # Objective. PEAK = nominal GA-adjusted metric (original behaviour).
        # ROBUST = fabrication yield under process sigma (fraction of Monte-Carlo
        # samples that pass all thresholds), with the nominal score as a tiny
        # tiebreaker so equal-yield candidates still prefer better metrics. This
        # makes the GA hunt for recipes that survive fab variation, not cliff-edge
        # peaks that look great nominally but fail most real devices.
        nominal_score = ga_score(kc, layer, metrics)
        if robust:
            yld, _ = _mc_yield(kc, layer, candidate_state, n_samples=mc_samples)
            score = yld + 1e-6 * nominal_score
        else:
            yld = None
            score = nominal_score

        # Log trial
        trial_entry = {
            "layer": layer,
            "trial_id": i,
            "seed": seed,
            "state": candidate_state,
            "metrics": metrics,
            "hash": result.get("hash", ""),
            "score": score,
            "nominal_score": nominal_score,
            "yield": yld,
        }
        kc.commit_trial(trial_entry)

        # Promote if passes thresholds
        if kc.passes_thresholds(layer, metrics):
            n_promoted += 1
            recipe_entry = {**trial_entry, "promoted_at_trial": i}
            kc.commit_recipe(recipe_entry)
            print(f"  [{i:4d}] PROMOTED! Score={score:.2f}  "
                  f"(total promotions: {n_promoted})")

        # Update best
        if score > best_score:
            best_score = score
            best_state = candidate_state
            best_trial = i
            best_yield = yld
            summary = _format_best(layer, metrics, nominal_score)
            ytxt = f" yield={yld*100:5.1f}% |" if yld is not None else ""
            print(f"  [{i:4d}] ★ New Best:{ytxt} {summary}")

        # Update population (keep best pop_size candidates)
        # Replace worst if population full
        if i < pop_size:
            population[i] = (candidate_state, score)
        else:
            worst_idx = min(range(len(population)), key=lambda x: population[x][1] or -1e18)
            if score > (population[worst_idx][1] or -1e18):
                population[worst_idx] = (candidate_state, score)

        # Progress report every 50 trials
        if (i + 1) % 50 == 0:
            print(f"  [{i+1:4d}/{budget}] Best so far: score={best_score:.2f} "
                  f"at trial {best_trial}, promotions={n_promoted}")

    print(f"\n{'─'*60}")
    print(f"Search complete: {budget} trials, {n_promoted} promotions")

    # Validate the champion's fabrication yield at high MC resolution (works for
    # both objectives — shows the *real* fab robustness of whatever was found).
    champ_yield = None
    if best_state is not None and _mc_yield is not None and layer in ("L", "PM", "E", "EM"):
        try:
            champ_yield, _ = _mc_yield(kc, layer, best_state, n_samples=2000)
        except Exception:
            champ_yield = None

    ytxt = f", fab-yield(2000 MC)={champ_yield*100:.1f}%" if champ_yield is not None else ""
    print(f"Best state (trial {best_trial}, score={best_score:.2f}{ytxt}):")
    print(json.dumps(best_state, indent=2))


def _format_best(layer, metrics, score):
    """One-line metric summary for progress output."""
    if layer == "L":
        mu   = metrics.get("mobility_cm2_Vs", 0)
        ioff = metrics.get("Ioff_A", 0)
        cryst = metrics.get("crystallization_risk", 1)
        return f"score={score:.2f} μ={mu:.2f} Ioff={ioff:.1e} cryst={cryst:.2f}"
    elif layer == "PM":
        dn  = metrics.get("delta_n", 0)
        k   = metrics.get("loss_k", 1)
        fom = metrics.get("fom", 0)
        return f"score={score:.2f} Δn={dn:.4f} k={k:.4e} FOM={fom:.1f}"
    elif layer == "E":
        pol  = metrics.get("polarization_uC_cm2", 0)
        kval = metrics.get("dielectric_constant_k", 0)
        fo   = metrics.get("_f_ortho", 0)
        return f"score={score:.2f} Pr={pol:.2f} k={kval:.1f} f_ortho={fo:.3f}"
    elif layer == "EM":
        d33  = metrics.get("d33_pC_N", 0)
        kt2  = metrics.get("coupling_kt2_pct", 0)
        stab = metrics.get("_phase_stability", 0)
        return f"score={score:.2f} d33={d33:.2f} kt2={kt2:.2f}% stab={stab:.3f}"
    else:
        return f"score={score:.2f}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Morphium GA Search — Tier 1.5 Physics"
    )
    parser.add_argument("--layer",  required=True, choices=list(GENERATORS.keys()),
                        help="Layer to optimise")
    parser.add_argument("--budget", type=int, default=500,
                        help="Number of simulation trials (default: 500)")
    parser.add_argument("--pop",    type=int, default=30,
                        help="Population size (default: 30)")
    parser.add_argument("--seed",   type=int, default=7,
                        help="Global random seed (default: 7)")
    parser.add_argument("--root",   default=".",
                        help="Project root directory (default: .)")
    parser.add_argument("--robust", action="store_true",
                        help="Optimise for fabrication YIELD under process sigma "
                             "(Monte-Carlo) instead of peak nominal metric.")
    parser.add_argument("--mc-samples", type=int, default=64, dest="mc_samples",
                        help="MC samples per candidate in --robust mode (default: 64). "
                             "Lower = faster search, higher = less noisy yield estimate.")
    args = parser.parse_args()

    random.seed(args.seed)

    kc = KernelClient(project_root=args.root)
    run_search(args.layer, args.budget, kc, pop_size=args.pop,
               robust=args.robust, mc_samples=args.mc_samples)
