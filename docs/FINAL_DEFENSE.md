# FINAL DEFENSE: MORPHIUM KERNEL (Architecture Audit)

**ROLE:** You are the Chief Technology Officer (CTO) of a Trillion-Dollar Semiconductor Foundry.
**TASK:** Perform a final "Go/No-Go" review of the Morphium Kernel v1.0 architecture before we commit to physical fabrication.

---

## 1. The Pivot: Why we rejected High-Speed ITZO
We initially targeted high-mobility Indium-Tin-Zinc-Oxide (ITZO).
*   **Simulation Result:** Mobility hit >50 cm²/Vs.
*   **The Catch:** Trap density exploded ($>10^{17} cm^{-3}$), leading to Subthreshold Swing > 2000 mV/dec. The device was a resistor, not a switch.
*   **Decision:** We reverted to **Indium-Gallium-Zinc-Oxide (IGZO)**.
*   **Conservative design reference:** `In:0.26 Ga:0.24 Zn:0.02 O:0.46` — the
    model's µ≈13 calibration anchor, used here deliberately as a conservative
    (worst-case) design value. NOTE (audit 2026-06-03): this composition has
    cation Zn≈0.05, *below* the literature-justified Zn≥0.10 floor, so it is NOT
    the recommended fab champion. The floor-compliant champion is In-rich
    (cation In0.63/Ga0.27/Zn0.10) at µ≈21 cm²/Vs (an extrapolation beyond the
    1:1:1 calibration); see `docs/CHAMPIONS.md`. The conservative 13.1 below
    only strengthens the robustness argument.
    *   **Mobility:** 13.1 cm²/Vs (Conservative reference).
    *   **SS:** 77 mV/dec (Excellent control).
    *   **Yield:** 100% at 10% process drift.

## 2. The Logic: Multi-Radix Logic (MRL)
We are not building binary (0/1). We are building Ratiometric Logic (0.0, 0.5, 1.0V).
*   **Validation:** We simulated an MRL Inverter using the `IGZO` physical model. Source code: `tools/multi_radix_sim.py`.
*   **Stress Test:** We applied **30% degradation** to the material (Mobility 13.1 -> 9.96) AND **50% Asymmetry** between the Driver and Load transistors.
*   **Result:** The logic level `0.5V` shifted by less than 0.01V. The circuit logic is robust against material variability.

## 3. The Physical Reality (Garage Fab)
We acknowledge the "Red Team" findings and have patched the process flow:
*   **ScAlN Peeling:** We now mandate a **20nm Molybdenum (Mo)** seed layer to orient the C-axis.
*   **Se Evaporation:** We mandate **in-situ Al2O3 capping** before breaking vacuum.
*   **IGZO Stoichiometry:** We enforce `Oxygen Ratio > 0.8` to prevent metallization.

## 4. The Material Stack (Frozen)

| Layer | Material | Function | Status |
|:---|:---|:---|:---|
| **L** | **IGZO** | Control Logic | **Robust (13.1 $\mu$)** |
| **E** | **HfZrO2** | Analog Memory | **Stable ($P_r$ 11.2)** |
| **EM** | **ScAlN** | Actuator | **Seed-Layer Protected** |
| **PM** | **Sb2Se3:Ge:Cl** | Photonics | **Doped Glass (GSST-like)** |
| **M** | **HfO2:DLC** | Latching | **Macro-Scale Ready** |

---

## YOUR VERDICT
Based on this corrected data:
1.  **Is the "Logic Pivot" (ITZO -> IGZO) scientifically sound?**
2.  **Does the "Ratiometric Logic" defense (Asymmetry Test) satisfy your concern about noise margins?**
3.  **Would you authorize a $2,000 seed fund for the first maskset?**
