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
        
        # Dielectric of the medium IN THE ELECTRODE GAP (the gap fill, NOT the
        # foglet shell/encapsulation): air/vacuum k=1 unless a solid fill is
        # declared via electrode_geometry.gap_dielectric. (Audit C-1: previously
        # mis-read structure.shell_material, applying e.g. HfO2 k=25 to an air
        # gap and inflating the latch force ~25x.)
        gap_fill = electrode.get("gap_dielectric", "air")
        k = 1.0
        for mat, props in self.dielectrics.items():
            if mat in gap_fill:
                k = props["k"]
                break
                
        # Parallel-plate electrostatic latch (gap medium per k above).
        # F = eps0*k*A*V^2/(2*d^2) = (C_gap)*V^2/(2*d); C_gap reused for release.
        eps0 = 8.854e-12
        cap_F = eps0 * k * area / gap
        force_N = cap_F * (voltage ** 2) / (2.0 * gap)
        force_mN = force_N * 1e3
        
        # Dry adhesion (fibrillar / van der Waals) — physical first pass.
        # (Audit M-4: previous model was dimensionally broken — energy mislabeled
        # as force, and pad_area cancelled so shear was geometry-independent.)
        pad_area = adhesion.get("pad_area_um2", 100.0) * 1e-12   # m^2
        W_adhesion = 0.10  # work-of-adhesion scale [J/m^2], generic vdW
        
        if adhesion.get("type") == "dry_gecko":
            W_adhesion = 0.50  # dense setal fibrils

        # Shear = vdW intimate-contact limit (W/z0) x real-contact fill x a
        # size-derating (larger pads -> more defects -> lower effective stress).
        # Calibrated so a dry_gecko pad at the 200 um^2 reference ~ 110 kPa
        # (Autumn et al. PNAS 2002, ~100 kPa setal-array shear). pad geometry
        # now produces a real optimizer gradient.
        _sigma0_kPa = (W_adhesion / 0.3e-9) / 1000.0          # W/z0, z0~0.3 nm
        shear_kPa = _sigma0_kPa * 6.6e-5 * ((200.0e-12 / max(pad_area, 1e-15)) ** 0.15)
        
        # Deterministic Noise
        if self.seed:
            noise = 1.0 + (random.uniform(-0.1, 0.1))
            force_mN *= noise
            shear_kPa *= noise
            
        return {
            "latch_normal_force_mN": round(force_mN, 3),
            "adhesion_shear_strength_kPa": round(shear_kPa, 2),
            "release_energy_uJ": round(0.5 * cap_F * (voltage**2) * 1e6, 9), # 0.5 C V^2, geometry-derived (M-5)
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
