# Architecture Freeze (v1.0.0)
**Locked Invariants for Morphium Kernel**

## 1. Contracts
*   **Layer E:** HfO2-based Ferroelectric Logic. (Metric: Polarization).
*   **Layer EM:** ScAlN Piezoelectric Actuation. (Metric: d33).
*   **Layer PM:** Sb2Se3 Phase-Change Photonics. (Metric: FOM).
*   **Layer L:** Oxide Semiconductor Logic. (Metric: Mobility).
*   **Layer M:** Electrostatic Latching. (Metric: Force).

## 2. Interface
*   All simulations MUST accept a `seed` and return a SHA-256 `hash`.
*   Ledger MUST be append-only.
*   Promotion MUST be gated by hard thresholds in `contract.yaml`.

## 3. Toolchain
*   **Discovery:** Genetic Algorithm (LoopAdapter).
*   **Validation:** Deterministic Re-simulation (Gatekeeper).
*   **Registry:** JSON Ledger.
