"""
Morphium Destruction Tester (Nuclear Edition)
Stresses ALL layers (E, EM, PM, L, M) by perturbing formulas and state.
Drifts up to 90%.
"""
import sys
import os
import json
import random
import re
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())
from MORPHIUM_KERNEL.src.morphium_kernel.kernel import KernelClient

def perturb_formula(formula, error_margin):
    """
    Parses 'Hf0.5Zr0.5O2' -> drifts numbers -> 'Hf0.53Zr0.47O2.1'
    """
    # Find all element-number pairs (e.g., 'Hf0.5')
    # Regex: ([A-Z][a-z]?) gets Element, ([0-9]*\.?[0-9]+)? gets Number (optional)
    
    def replacer(match):
        element = match.group(1)
        num_str = match.group(2)
        
        if not num_str:
            # If no number (e.g. 'O'), assume 1.0, drift it, append new number
            val = 1.0
            val *= random.uniform(1.0 - error_margin, 1.0 + error_margin)
            return f"{element}{val:.2f}"
        
        val = float(num_str)
        val *= random.uniform(1.0 - error_margin, 1.0 + error_margin)
        return f"{element}{val:.2f}"

    # Regex matches Element followed optionally by Number
    new_formula = re.sub(r'([A-Z][a-z]?)([0-9]*\.?[0-9]+)?', replacer, formula)
    return new_formula

def perturb_state(layer, state, error_margin):
    new_state = json.loads(json.dumps(state))
    
    # 1. Formula String Layers (E, EM, PM)
    if "formula" in new_state:
        new_state["formula"] = perturb_formula(new_state["formula"], error_margin)
        
    # 2. Structured Layers (L, M)
    if layer == "L":
        if "materials" in new_state and "channel_composition" in new_state["materials"]:
            comp = new_state["materials"]["channel_composition"]
            for k in comp:
                comp[k] *= random.uniform(1.0 - error_margin, 1.0 + error_margin)
    
    if layer == "M":
        if "foglet" in new_state:
            # Drift Geometry
            geo = new_state["foglet"]["latching"]["electrode_geometry"]
            geo["gap_nm"] *= random.uniform(1.0 - error_margin, 1.0 + error_margin)
            # Drift Voltage (Power Supply Noise)
            pwr = new_state["foglet"]["power"]
            pwr["max_voltage_V"] *= random.uniform(1.0 - error_margin, 1.0 + error_margin)

    return new_state

def run_destruction(layer, state, kc):
    print(f"\n=== Destructive Testing: Layer {layer} ===")
    print(f"Base State: {str(state)[:60]}...")
    
    for stress in [0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90]:
        failures = 0
        iterations = 50 # Statistical sample
        
        for i in range(iterations):
            drifted = perturb_state(layer, state, stress)
            try:
                # Some drifts might cause regex errors in sim, count as fail
                res = kc.simulate(layer, drifted, seed=i)
                metrics = res.get("metrics", res.get("data"))
                
                # Check Hard Thresholds
                if not kc.passes_thresholds(layer, metrics):
                    failures += 1
                    if failures == 1:
                        print(f"DEBUG FAIL: {json.dumps(metrics)}")
            except Exception:
                failures += 1 # Simulation crash = Material Failure
        
        yield_rate = 100 * (1 - (failures / iterations))
        bar = "#" * int(yield_rate / 10)
        print(f"Stress {stress*100:>2.0f}%: Yield {yield_rate:>5.1f}% [{bar:<10}]")
        
        if yield_rate < 50:
            print(f"--> FAILED at {stress*100}% Drift (Continuing...)")
            # return  <-- Disabled to see full destruction

def main():
    kc = KernelClient()
    
    with open("MORPHIUM_KERNEL/artifacts/GOLDEN_IMAGE.json") as f:
        golden = json.load(f)
        
    for layer in ["E", "EM", "PM", "L", "M"]:
        # Handle Golden Image structure (flat vs nested)
        if layer in golden["layers"]:
            data = golden["layers"][layer]
            if "state" in data and "formula" in data["state"]:
                # E, EM, PM style in Golden Image V1
                state = data["state"]
            elif "state" in data and "state" in data["state"]:
                 # L, M style (nested state)
                 state = data["state"]["state"]
            elif "state" in data:
                 # Generic fallback
                 state = data["state"]
            else:
                print(f"Skipping {layer}: Unknown format")
                continue
                
            run_destruction(layer, state, kc)

if __name__ == "__main__":
    main()
