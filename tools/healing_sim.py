"""
Morphium-H Healing Simulator
Demonstrates Self-Repair of Logic Gates.
"""
import sys
import os
import json
import copy
import math

# Add project root
sys.path.append(os.getcwd())
from MORPHIUM_KERNEL.src.morphium_kernel.kernel import KernelClient
# Import perturb_state - try diverse locations
try:
    from MORPHIUM_KERNEL.tools.stress_test import perturb_state
except ImportError:
    try:
        from tools.stress_test import perturb_state
    except ImportError:
        from stress_test import perturb_state

def normalize_composition(comp):
    total = sum(max(v, 0.0) for v in comp.values())
    if total <= 0:
        return comp
    for el in comp:
        comp[el] = max(comp[el], 0.0) / total
    return comp

def estimate_healing_efficiency(damaged_comp, champ_comp, field_v_cm, pulse_count, temp_c):
    damaged_m = damaged_comp.get("In", 0.0) + damaged_comp.get("Ga", 0.0) + damaged_comp.get("Zn", 0.0) + damaged_comp.get("Sn", 0.0)
    champ_m = champ_comp.get("In", 0.0) + champ_comp.get("Ga", 0.0) + champ_comp.get("Zn", 0.0) + champ_comp.get("Sn", 0.0)
    damaged_o_ratio = damaged_comp.get("O", 0.0) / max(damaged_m, 1e-9)
    champ_o_ratio = champ_comp.get("O", 0.0) / max(champ_m, 1e-9)
    oxygen_deficit = max(champ_o_ratio - damaged_o_ratio, 0.0)
    structural_error = sum(abs(champ_comp[k] - damaged_comp.get(k, 0.0)) for k in champ_comp)

    temp_k = temp_c + 273.15
    thermal_factor = math.exp(-300.0 / max(temp_k, 1.0))
    field_factor = field_v_cm / 1.5e5
    pulse_factor = math.sqrt(max(pulse_count, 1))
    drive = field_factor * pulse_factor * (1.0 + 2.0 * oxygen_deficit) * (1.0 + structural_error)

    # Garage-fab bound: single pulse-train healing saturates below full repair.
    max_eff = 0.65
    eff = max_eff * (1.0 - math.exp(-0.20 * thermal_factor * drive))
    return max(0.0, min(max_eff, eff))

def run_healing_test():
    kc = KernelClient()

    # Load Champion L State
    with open("MORPHIUM_KERNEL/artifacts/GOLDEN_IMAGE.json") as f:
        golden = json.load(f)
    champ_state = golden["layers"]["L"]["state"]["state"] # Nested state

    print("--- Morphium-H Healing Test (30% Drift) ---")

    iterations = 100
    failures_baseline = 0
    failures_healed = 0
    healing_eff_sum = 0.0

    field_v_cm = 2.0e5
    pulse_count = 24
    temp_c = 60.0

    for i in range(iterations):
        # 1. Induce Damage (30% Drift)
        damaged_state = perturb_state("L", champ_state, 0.30)

        # 2. Simulate Baseline (No H)
        res_base = kc.simulate("L", damaged_state, seed=i)
        metrics_base = res_base["metrics"]

        if not kc.passes_thresholds("L", metrics_base):
            failures_baseline += 1

            # 3. Simulate Healing (Morphium-H)
            # Nonlinear field-drive approximation:
            # stronger electric field, longer pulse train, and higher temperature
            # increase ionic migration toward the champion stoichiometry.
            healed_state = copy.deepcopy(damaged_state)
            comp = healed_state["materials"]["channel_composition"]

            champ_comp = champ_state["materials"]["channel_composition"]
            eta = estimate_healing_efficiency(comp, champ_comp, field_v_cm, pulse_count, temp_c)
            healing_eff_sum += eta

            for el in comp:
                diff = champ_comp[el] - comp[el]
                # WOx reservoir primarily tunes oxygen chemical potential.
                # Metals are only weakly corrected by coupled rebalancing.
                if el == "O":
                    local_eta = min(eta * 1.10, 0.95)
                else:
                    local_eta = min(eta * 0.35, 0.35)
                comp[el] += diff * local_eta

            normalize_composition(comp)

            res_healed = kc.simulate("L", healed_state, seed=i)
            metrics_healed = res_healed["metrics"]

            if not kc.passes_thresholds("L", metrics_healed):
                failures_healed += 1

    yield_base = 100 * (1 - failures_baseline/iterations)
    yield_healed = 100 * (1 - failures_healed/iterations)
    recovered = failures_baseline - failures_healed
    conditional_recovery = 0.0 if failures_baseline == 0 else 100 * (recovered / failures_baseline)
    avg_eta = 0.0 if failures_baseline == 0 else (healing_eff_sum / failures_baseline)

    print(f"Baseline Yield (No H): {yield_base:.1f}%")
    print(f"Healed Yield (With H): {yield_healed:.1f}%")
    print(f"Yield Recovery: +{yield_healed - yield_base:.1f}%")
    print(f"Recovered Failed Samples: {recovered}/{failures_baseline}")
    print(f"Conditional Recovery Rate: {conditional_recovery:.1f}%")
    print(f"Average Healing Efficiency (eta): {avg_eta:.3f}")

if __name__ == "__main__":
    run_healing_test()
