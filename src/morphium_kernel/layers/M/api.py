"""
Morphium-M Layer API (Modular Mechanics)
Implements the contract defined in contract.yaml.
"""
import random
import re
import json
import math
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
                
        # Latch force depends on the latch MECHANISM. Electrostatic latches are
        # strong but wear by dielectric field stress (low endurance); mechanical
        # micro-interlocks have no field-stress wear (orders-higher endurance) at
        # the cost of engagement actuation; hybrid uses a mechanical hold with a
        # brief electrostatic assist (high endurance, low breakdown duty).
        latch_type = latching.get("type", "electrostatic")
        eps0 = 8.854e-12
        cap_F = eps0 * k * area / gap
        force_es_N = cap_F * (voltage ** 2) / (2.0 * gap)        # parallel-plate
        SIGMA_LATCH_PA = 2.0e6                                   # micro-interlock stress (partial engagement)
        force_mech_N = SIGMA_LATCH_PA * area
        if latch_type == "mechanical":
            force_N, uses_field = force_mech_N, False
        elif latch_type == "hybrid":
            force_N, uses_field = force_es_N + force_mech_N, True
        else:  # electrostatic
            force_N, uses_field = force_es_N, True
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
        
        # ------------------------------------------------------------------
        # COMPOSITE COUPLINGS. A foglet's capabilities derive from the E/EM/PM
        # stack beneath it (contract: required_layers [E, EM, PM]). The relevant
        # sub-layer champion metrics arrive in state["stack"] (defaults let the
        # model still run standalone). EM -> actuation/locomotion; E -> controller
        # (nonvolatile-state endurance); PM -> optical comms. This realises the
        # dependency the contract declared but the old stub ignored.
        # ------------------------------------------------------------------
        stack = state.get("stack", {})
        em_d33    = stack.get("EM_d33_pC_N", 20.0)         # pm/V piezo coefficient
        e_endur   = stack.get("E_endurance_cycles", 1e10)  # controller NVM endurance
        pm_loss_k = stack.get("PM_loss_k", 1e-5)           # photonic loss (comms)

        # --- Foglet mass & weight ---
        form   = foglet.get("form_factor", {})
        L_um   = form.get("characteristic_length_um", 100.0)
        mass_ug = form.get("mass_ug", power.get("mass_ug", None))
        if mass_ug is None:
            mass_ug = 2000.0 * (L_um * 1e-6) ** 3 * 1e9    # m=rho*L^3, rho~2000 kg/m3
        weight_N = mass_ug * 1e-9 * 9.81

        # --- Piezo actuation / locomotion (driven by EM d33) ---
        # Amplified actuator (multilayer stack x lever, gain ~1e3): step
        # displacement = d33[pm/V] * V * gain. Better EM champion (higher d33)
        # -> larger step -> faster, lower energy per distance.
        ACT_GAIN = 1000.0
        step_size_um   = em_d33 * voltage * ACT_GAIN / 1e6
        C_act          = max(cap_F, 1e-15) * 10.0          # actuator cap class
        step_energy_uJ = 0.5 * C_act * (voltage ** 2) * 1e6
        max_power_mW   = power.get("max_power_mW", 1.0)
        step_rate_Hz   = min((max_power_mW * 1e-3) / max(step_energy_uJ * 1e-6, 1e-15), 1e4)
        max_speed_mm_s = step_size_um * step_rate_Hz / 1000.0

        # --- Payload ratio: self-weights the latch can hold ---
        payload_ratio = force_N / max(weight_N, 1e-18)

        # --- cycle_life: latch endurance (mechanism-dependent) ---
        field_V_per_nm = (voltage / (gap * 1e9)) if uses_field else 0.0
        bd_margin  = (1.0 / field_V_per_nm) if field_V_per_nm > 0 else 1e6   # E_bd(1.0)/E_op
        if latch_type == "mechanical":
            cyc_latch = 1.0e8                    # mechanical fatigue, no field wear
        elif latch_type == "hybrid":
            cyc_latch = 5.0e7                    # mechanical hold + brief field pulses
        else:                                    # electrostatic: field-stress power law
            cyc_latch = 1e3 * (max(bd_margin, 0.1) ** 4)
        cycle_life = min(cyc_latch, 1e12, e_endur)   # E-layer NVM endurance caps it

        # --- failure_rate_pct (heaviest contract metric): combine independent
        #     failure modes via soft margins. Breakdown applies only to
        #     field-using latches (and at reduced duty for hybrid). ---
        def _soft_fail(margin, sharp):
            z = sharp * (margin - 1.0)
            if z > 50.0:
                return 0.0
            if z < -50.0:
                return 1.0
            return 1.0 / (1.0 + math.exp(z))
        if not uses_field:
            p_bd = 0.0
        elif latch_type == "hybrid":
            p_bd = 0.3 * _soft_fail(bd_margin, 6.0)   # brief assist pulses -> low duty
        else:
            p_bd = _soft_fail(bd_margin, 6.0)
        hold_margin = force_N / max(weight_N * 10.0, 1e-18)        # hold >= 10x weight
        p_latch = _soft_fail(hold_margin, 4.0)
        p_act   = _soft_fail(payload_ratio / 10.0, 4.0)           # lift >= 10x weight
        failure_rate_pct = (1.0 - (1.0 - p_bd) * (1.0 - p_latch) * (1.0 - p_act)) * 100.0

        # --- swarm reconfiguration: time to traverse a 1 mm reference at max_speed ---
        reconfiguration_time_s = 1.0 / max(max_speed_mm_s, 1e-6)

        # --- Deterministic noise (deposition / contact variability) ---
        if self.seed:
            n = 1.0 + random.uniform(-0.1, 0.1)
            force_mN *= n; shear_kPa *= n
            step_size_um *= n; max_speed_mm_s *= n
            failure_rate_pct = min(failure_rate_pct * n, 100.0)

        release_uJ = 0.0 if latch_type == "mechanical" else 0.5 * cap_F * (voltage**2) * 1e6
        return {
            "latch_normal_force_mN":       round(force_mN, 3),
            "adhesion_shear_strength_kPa": round(shear_kPa, 2),
            "release_energy_uJ":           round(release_uJ, 9),
            "cycle_life":                  int(cycle_life),
            "_latch_type":                 latch_type,
            "step_size_um":                round(step_size_um, 4),
            "step_energy_uJ":              round(step_energy_uJ, 9),
            "max_speed_mm_s":              round(max_speed_mm_s, 4),
            "payload_ratio":               round(payload_ratio, 2),
            "failure_rate_pct":            round(failure_rate_pct, 3),
            "reconfiguration_time_s":      round(reconfiguration_time_s, 4),
            "_em_d33_used":                em_d33,
            "_mass_ug":                    round(mass_ug, 6),
            "_field_V_per_nm":             round(field_V_per_nm, 4),
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
