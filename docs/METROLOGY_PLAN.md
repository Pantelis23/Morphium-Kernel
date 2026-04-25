# Morphium Metrology Plan (v1.0)
**Objective:** Validate simulation champions with physical measurements.

## Layer L (Oxide Logic)
**Target:** IGZO TFT with $\mu > 15$ cm²/V·s.

### 1. DC Characterization (Id-Vg, Id-Vd)
*   **Instrument:** Keithley 4200-SCS or similar Parameter Analyzer.
*   **Sweep:**
    *   Gate Voltage ($V_g$): -10V to +20V (Step 0.5V).
    *   Drain Voltage ($V_d$): 0.1V (Linear), 10V (Saturation).
*   **Extraction Script:** `lab/scripts/extract_tft_metrics.py`.
*   **Metrics to Extract:**
    *   **Mobility ($\mu_{sat}$):** From $\sqrt{I_d}$ vs $V_g$ slope.
    *   **Threshold Voltage ($V_{th}$):** X-axis intercept.
    *   **Subthreshold Swing (SS):** Inverse slope of $\log(I_d)$ vs $V_g$.
    *   **On/Off Ratio:** $I_{max} / I_{min}$.

### 2. Stability (Bias Stress)
*   **Method:** Positive Gate Bias Stress (PBS).
*   **Condition:** $V_g = +20V$ for 3600s at Room Temp.
*   **Pass Criteria:** $\Delta V_{th} < 1.0V$.

---

## Layer M (Modular Mechanics)
**Target:** Electrostatic Latch Force > 5 mN.

### 1. Force-Voltage Profiling
*   **Instrument:** Load Cell (e.g., Instron) + High Voltage Source (Keithley 2410).
*   **Setup:** Macro-scale parallel plate capacitor (1cm²) with defined gap (spacers).
*   **Sweep:** 0V to 100V.
*   **Measure:** Normal Force vs Voltage.
*   **Metric:** Force Constant $k_{el} = F / V^2$.

### 2. Adhesion Testing
*   **Method:** Shear Pull Test.
*   **Setup:** Drag Foglet shell material against glass substrate.
*   **Metric:** Shear Strength (kPa).

---

## Layer PM (Photonics)
**Target:** $\Delta n > 1.0$ at 1550nm.

### 1. Ellipsometry
*   **Instrument:** Woollam Ellipsometer.
*   **Method:** Measure $\Psi$ and $\Delta$ vs Wavelength.
*   **Model:** Tauc-Lorentz Oscillator.
*   **Metric:** Extract $n$ and $k$ for Amorphous vs Crystalline states.
