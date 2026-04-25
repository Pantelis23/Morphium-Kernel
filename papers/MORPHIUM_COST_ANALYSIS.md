# Morphium Material Cost Analysis
**Project:** Morphium Kernel
**Date:** Feb 2026

## 1. Material Stack Overview
The stack consists of three functional layers deposited sequentially via ALD/CVD.

| Layer | Function | Material | Thickness | Critical Element |
|:---|:---|:---|:---|:---|
| **Morphium-E** | Logic/Memory | Hf0.5Zr0.5O2 | 10 nm | Hafnium (Hf) |
| **Morphium-EM** | Actuation | ScAlN | 50 nm | Scandium (Sc) |
| **Morphium-PM** | Photonics | Sb2Se3:Ge:In:Sn:Cl | 200 nm | Selenium (Se) |

---

## 2. Cost Breakdown (Precursor Level)

### 2.1 Morphium-PM (Photonics)
*   **Base:** Antimony Selenide (`Sb2Se3`).
*   **Precursors:**
    *   **Sb:** `Sb(OEt)3` (Triethoxyantimony). **Price:** ~$14.00 / gram. (Low).
    *   **Se:** `(TMS)2Se` (Bis(trimethylsilyl)selenide). **Price:** ~$500 / gram. (Very High).
*   **Cost Driver:** The Selenium precursor is a specialty chemical.
*   **Reduction Strategy:** 
    *   Switch to **H2Se Gas** (Hydrogen Selenide). Price drops to <$0.10 / gram (Bulk Gas). *Note: Highly Toxic.*
    *   Switch to **Thermal Evaporation** of Elemental Selenium ($20 / kg).

### 2.2 Morphium-EM (Mechanics)
*   **Base:** Scandium Aluminum Nitride (`ScAlN`).
*   **Precursors:**
    *   **Sc:** `Sc(thd)3`. **Price:** ~$230.00 / gram. (High).
    *   **Al:** `TMA`. **Price:** Commodity ($1 / gram).
*   **Cost Driver:** Scandium is a Rare Earth element, and the `thd` ligand is complex.
*   **Reduction Strategy:**
    *   Switch to **Sputtering** (PVD) using a `Sc-Al` alloy target. Target cost is ~$5000 but lasts for 10,000 wafers. Cost per wafer drops to cents.
    *   Source `Sc(Cp)3` (Cyclopentadienyl) which is slightly cheaper than `thd`.

### 2.3 Morphium-E (Electronics)
*   **Base:** Hafnium Zirconium Oxide (`HZO`).
*   **Precursors:** `TEMAH`, `TEMAZ`.
*   **Price:** ~$50 / gram.
*   **Status:** Standard semiconductor commodity. No optimization needed.

---

## 3. Total Stack Estimate (Per 300mm Wafer)
Assuming 100% yield and standard ALD efficiency (20% utilization).

*   **Lab Scale (Precursors):**
    *   PM (200nm): $150.00 (Due to Se precursor)
    *   EM (50nm): $50.00 (Due to Sc precursor)
    *   E (10nm): $5.00
    *   **Total:** **$205.00 / wafer** (Expensive for production).

*   **Fab Scale (Gas/Targets):**
    *   PM (H2Se Gas): $0.50
    *   EM (Sputtering): $2.00
    *   E (TEMAH): $1.00
    *   **Total:** **$3.50 / wafer** (Extremely Competitive).

## 4. Conclusion
For the prototype (Lab), the cost is dominated by the **Selenium Precursor**.
For production (Fab), the cost is negligible. The barrier is **Safety** (H2Se handling) and **Capital** (Sputtering tool for Sc).
