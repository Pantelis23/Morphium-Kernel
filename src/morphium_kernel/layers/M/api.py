"""
Morphium-M Layer API (Modular Mechanics)
Implements the contract defined in contract.yaml.
"""
import random
import re
import json
import hashlib

class MorphiumSimulatorM:
    def __init__(self, seed=None):
        self.seed = seed
        if seed: random.seed(seed)
        
        self.dielectrics = {
            "SiO2": {"k": 3.9},
            "Al2O3": {"k": 9.0},
            "HfO2": {"k": 25.0},
            "TiO2": {"k": 80.0},
            "SrTiO3": {"k": 300.0}
        }
        
    def simulate(self, state):
        foglet = state.get("foglet", {})
        latching = foglet.get("latching", {})
        adhesion = foglet.get("adhesion", {})
        power = foglet.get("power", {})
        
        # Electrostatic Latching
        electrode = latching.get("electrode_geometry", {"area_um2": 100.0, "gap_nm": 100.0})
        voltage = power.get("max_voltage_V", 20.0)
        
        area = electrode.get("area_um2", 100.0) * 1e-12
        gap = electrode.get("gap_nm", 100.0) * 1e-9
        
        # Determine K value from frame/shell material hints (simplified)
        shell = foglet.get("structure", {}).get("shell_material", "SiO2")
        k = 1.0
        for mat, props in self.dielectrics.items():
            if mat in shell:
                k = props["k"]
                break
                
        # F = (eps0 * k * A * V^2) / (2 * d^2)
        eps0 = 8.854e-12
        force_N = (eps0 * k * area * (voltage**2)) / (2 * (gap**2))
        force_mN = force_N * 1e3
        
        # Adhesion (Van der Waals)
        pad_area = adhesion.get("pad_area_um2", 100.0) * 1e-12
        surface_energy = 0.05 # J/m2 (Generic polymer)
        
        if adhesion.get("type") == "dry_gecko":
            surface_energy = 0.5 # Enhanced
            
        adhesion_force = surface_energy * pad_area * 1e6 # Scaled heuristic
        shear_kPa = (adhesion_force / pad_area) / 1000.0
        
        # Deterministic Noise
        if self.seed:
            noise = 1.0 + (random.uniform(-0.1, 0.1))
            force_mN *= noise
            shear_kPa *= noise
            
        return {
            "latch_normal_force_mN": round(force_mN, 3),
            "adhesion_shear_strength_kPa": round(shear_kPa, 2),
            "release_energy_uJ": round(0.5 * 100e-12 * (voltage**2) * 1e6, 3), # CV^2/2
            "cycle_life": 10000,
            "seed": self.seed
        }

def execute(state):
    seed = state.get("seed", 42)
    sim = MorphiumSimulatorM(seed=seed)
    metrics = sim.simulate(state)
    
    result = {
        "state": state,
        "metrics": metrics,
        "hash": hashlib.sha256(json.dumps(metrics, sort_keys=True).encode()).hexdigest()
    }
    return result

if __name__ == "__main__":
    test_state = {
        "foglet": {
            "structure": {"shell_material": "HfO2:DLC"},
            "latching": {
                "type": "electrostatic",
                "electrode_geometry": {"area_um2": 100.0, "gap_nm": 50.0}
            },
            "adhesion": {"type": "dry_gecko", "pad_area_um2": 200.0},
            "power": {"max_voltage_V": 40.0}
        },
        "seed": 201
    }
    print(json.dumps(execute(test_state), indent=2))
