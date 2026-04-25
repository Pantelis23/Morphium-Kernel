"""
Multi-Radix Logic Simulator
Simulates a Multi-Radix Inverter running on Morphium-L (IGZO).
Applies Stress to verify robustness of the Logic Level.
"""
import sys
import os
import json
import random
from pathlib import Path

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from src.morphium_kernel.kernel import KernelClient
except ImportError:
    from morphium_kernel.src.morphium_kernel.kernel import KernelClient

def get_tft_current(v_gs, v_ds, props):
    mu = props["mobility_cm2_Vs"]
    # ... (rest is fine)
    vth = props["Vth_V"]
    ss = props["SS_mV_dec"]
    
    # Geometry
    W = 10.0 # um
    L = 5.0  # um
    Cox = 3.45e-7 # F/cm2 (20nm Al2O3)
    
    # Subthreshold
    if v_gs < vth:
        return props["Ioff_A"] * (10 ** ((v_gs - vth) / (ss/1000.0)))
    
    # Above Threshold
    k = (W/L) * mu * Cox
    
    if v_ds < (v_gs - vth):
        # Linear Region
        ids = k * ((v_gs - vth) * v_ds - (v_ds**2)/2)
    else:
        # Saturation Region
        ids = k * ((v_gs - vth)**2) / 2
        
    return max(ids, props["Ioff_A"])

def simulate_inverter(voltage_in, supply_voltage, driver_props, load_props):
    # Numerical solver for Vout
    best_vout = 0.0
    min_diff = 1e9
    
    # Sweep Vout to find equilibrium
    for v_out_candidate in [i * supply_voltage / 100.0 for i in range(101)]:
        # Driver: Vgs = Vin, Vds = Vout
        i_driver = get_tft_current(voltage_in, v_out_candidate, driver_props)
        
        # Load (Diode): Vgs = Vdd - Vout, Vds = Vdd - Vout
        v_load_drive = supply_voltage - v_out_candidate
        # Use LOAD PROPS here
        i_load = get_tft_current(v_load_drive, v_load_drive, load_props)
        
        diff = abs(i_driver - i_load)
        if diff < min_diff:
            min_diff = diff
            best_vout = v_out_candidate
            
    return best_vout

def run_simulation():
    kc = KernelClient()
    
    # Load Champion L State
    with open("MORPHIUM_KERNEL/artifacts/GOLDEN_IMAGE.json") as f:
        golden = json.load(f)
    champ_state = golden["layers"]["L"]["state"]["state"]
    
    print("--- Multi-Radix Logic Simulation (Inverter) ---")
    print("Input Levels: 0.0V, 0.5V, 1.0V (Target: 1.0V, 0.5V, 0.0V)")
    
    # Get Base Properties
    res = kc.simulate("L", champ_state)
    base_props = res["metrics"]
    
    # Define MRL Levels
    levels = [0.0, 0.5, 1.0]
    supply = 1.0
    
    print("\n[Base Material]")
    for vin in levels:
        vout = simulate_inverter(vin, supply, base_props, base_props)
        print(f"  Vin: {vin:.1f}V -> Vout: {vout:.2f}V")
        
    # STRESS TEST (30% Drift)
    print("\n[Stressed Material - 30% Drift]")
    
    # Perturb State
    try:
        from tools.stress_test import perturb_state
    except ImportError:
        # Fallback if running from root
        from stress_test import perturb_state
    
    stressed_state = perturb_state("L", champ_state, 0.30)
    
    res_stress = kc.simulate("L", stressed_state)
    stress_props = res_stress["metrics"]
    
    print(f"  Drifted Mobility: {base_props['mobility_cm2_Vs']} -> {stress_props['mobility_cm2_Vs']}")
    
    for vin in levels:
        vout = simulate_inverter(vin, supply, stress_props, stress_props)
        print(f"  Vin: {vin:.1f}V -> Vout: {vout:.2f}V")
        
    # Check Linearity
    mid_out = simulate_inverter(0.5, supply, stress_props, stress_props)
    if 0.4 <= mid_out <= 0.6:
        print("\nRESULT: PASS. Logic is robust.")
    else:
        print("\nRESULT: FAIL. Linearity lost.")

    print("\n[Asymmetry Test - Driver Degrades 50%]")
    bad_driver = stress_props.copy()
    bad_driver["mobility_cm2_Vs"] *= 0.5
    
    for vin in levels:
        vout = simulate_inverter(vin, supply, bad_driver, stress_props)
        print(f"  Vin: {vin:.1f}V -> Vout: {vout:.2f}V")
        
    mid_asym = simulate_inverter(0.5, supply, bad_driver, stress_props)
    if 0.4 <= mid_asym <= 0.6:
        print("RESULT: PASS. Ratio Logic holds.")
    else:
        print(f"RESULT: FAIL. Skewed to {mid_asym:.2f}V. Needs Calibration.")

if __name__ == "__main__":
    run_simulation()
