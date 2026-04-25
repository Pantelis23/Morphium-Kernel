# Morphium Fabrication Plan (v1.0)
**Objective:** Validate the **Multi-Radix Logic (MRL)** and **Modular Mechanics** using de-risked materials.

---

## 1. Demo A: Morphium-L (MRL Logic Transistor)
**Goal:** Validate **Multi-Radix Logic** capability.
**Requirement:** High Linearity, Low Hysteresis (Drift < 0.05V).

### 1.1 Material Strategy (Risk Reduced)
*   **Champion (High Performance):** `IGZO` (In-Rich: 60% In). $\mu \approx 30$.
*   **Safe Mode (High Stability):** `IGZO` (Balanced: 1:1:1). $\mu \approx 10$.
    *   *Note:* Start with Safe Mode to verify the mask set.

### 1.2 Material Stack
| Layer | Material | Method | Thickness | Function |
|:---|:---|:---|:---|:---|
| **Substrate** | Glass | Clean | 0.7 mm | Base |
| **Gate** | Cr / Au | Sputter | 50 nm | Bottom Gate |
| **Dielectric** | **Al2O3** | ALD | 20 nm | Stable, High Breakdown |
| **Channel** | **IGZO** | PLD / Sputter | 30 nm | The MRL Switch |
| **S/D Metal** | Ti / Au | Sputter | 50 nm | Contacts |
| **Passivation** | **Al2O3** | ALD | 10 nm | **CRITICAL:** Prevents O2/H2O degradation |

### 1.3 Testing MRL Logic
Standard binary testing (On/Off) is insufficient. We must test **Linearity**.
*   **Test:** Sweep $V_{gate}$ from 0V to 5V.
*   **Measure:** $I_{drain}$.
*   **Pass Criteria:** The $I_d - V_g$ curve must be smooth and monotonic (no kinks) to support intermediate voltage levels (e.g. 0.3V, 0.6V, 0.9V).

---

## 2. Demo B: Morphium-EM (Macro Actuator)
**Goal:** Validate Actuation Force.

### 2.1 Material Strategy
*   **Champion:** `Sc0.99...N`. (High risk of phase collapse).
*   **Safe Mode:** **`Sc0.30Al0.70N`**.
*   **Stress Management:** **Seed Layer Required.**
    *   Deposit 20nm **Molybdenum (Mo)** or **Platinum (Pt)** before ScAlN to orient the C-axis and reduce lattice mismatch strain.

---

## 3. Demo C: Morphium-PM (Photonic Switch)
**Goal:** Validate Index Switching.

### 3.1 Mitigation
*   **Se-Loss:** Selenium evaporates easily.
*   **Fix:** **In-situ Capping**. Do not break vacuum after depositing `Sb2Se3`. Immediately deposit 10nm `SiO2` or `Al2O3` cap layer to seal the stoichiometry.

---

## 4. Execution Sequence
1.  **Run 1 (Calibration):** Fabricate "Safe Mode" materials. Verify tools work.
2.  **Run 2 (Champion):** Fabricate "Champion" materials (`In-Rich IGZO`, `Sc-Rich ScAlN`).
3.  **Measurement:** Characterize MRL Linearity.
