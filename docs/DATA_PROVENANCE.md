# Data Provenance & Trust

**Last updated: 2026-06-03.** This file states, honestly, what every key number in
Morphium is and how much to trust it. It is the companion to
[`AUDIT_2026-06-03.md`](AUDIT_2026-06-03.md) (the adversarial audit) and
[`CHAMPIONS.md`](CHAMPIONS.md) (the current champions).

## The one thing to understand first

**Everything here is *simulation*, not laboratory measurement.** The physics
models are calibrated to *published literature*, not to in-house fabrication. The
"gatekeeper" and words like "verified"/"blessed" mean a champion is
**reproducibly re-derivable** from the ledger and **passes the contract
thresholds** — a *reproducibility* guarantee, **not** a physical one. No Morphium
material has been fabricated or measured. Read every number below as
"best-available model estimate," with the trust tag telling you how solid the
*model/calibration* behind it is.

## Trust tags

| Tag | Meaning |
|-----|---------|
| **calibrated** | model reproduces a literature anchor closely; small/zero correction; tight uncertainty |
| **lit-grounded** | magnitudes and directions are literature-anchored, but extrapolated or single/few-point |
| **heuristic** | physically-motivated but uncalibrated proxy; treat as order-of-magnitude |
| **speculative** | direction plausible, magnitude unsupported by direct data — flagged in code |

## Per-metric provenance

### Optical / electrical headline metrics

| Layer | Metric | Champion value | Trust | Basis / caveat |
|-------|--------|---------------|-------|----------------|
| E | Pr (polarization) | ~17.6 µC/cm² | **calibrated** ±25% | Müller 2012 10nm HZO (Pr~17); residual = wake-up cycling (not modelled) |
| E | dielectric k | ~30 | **calibrated** | in 27–32 lit range |
| EM | d33 | ~22 pC/N (peak ~26) | **calibrated** ±25% | Akiyama 2009 (27.6), Mertin 2017 (26.9–27.3); model rescaled (audit M-6) |
| PM | Δn | ~0.75 | **calibrated** ±18% | Delaney 2020/2021 (0.765), OME 2022 (0.823) |
| PM | loss_k | ~5e-6 | **lit-grounded** | Sb₂Se₃ k<1e-5 at 1550nm; model floor fixed (audit M-2) |
| PM | FOM (Δn/k) | ~1e5 | **not a discriminator** | huge because k≈real; **Δn≥0.30 is the binding gate**, not FOM (audit m-6) |
| L | mobility | ~21 cm²/Vs | **lit-grounded** ±28% | In-rich a-IGZO 40–48 (Lee/Cho 2018); model is *conservative* (~2× low) — a documented, safe under-estimate |
| L | SS | ~120 mV/dec | **lit-grounded** | real a-IGZO 100–200; interface-trap term + phi offset |
| M | latch force | ~0.28 mN (air gap) | **lit-grounded** | parallel-plate; air-gap dielectric (audit C-1 fixed the 25× shell-k bug) |
| M | adhesion shear | ~110 kPa (gecko) | **heuristic** | calibrated to Autumn 2002 ~100 kPa; first-pass contact model |

### Operational endurance / cycle life (the reliability axis)

| Layer | Metric | Value | Trust | Basis / caveat |
|-------|--------|-------|-------|----------------|
| E | endurance_cycles | ~1e10 | **calibrated** | HZO P-E cycling 1e9–1e11 (Ru/HZO >1.2e11) |
| PM | cycling_endurance | up to 1e8 | **lit-grounded** | **geometry-driven**: integrated Sb₂Se₃ 1e3–1e6 (Fang 2021); record 1e8 via nanostructuring (Dutta 2026); composition only ~×2; Cl benefit **speculative** (no PCM data) |
| EM | actuation_endurance | ~1e12 | **lit-grounded** | sub-coercive piezo is ~fatigue-free (AlN MEMS); Jung 2025, Cho 2025. **Ferroelectric full-switching would be ~1e8** — not the foglet's regime |
| L | operational_endurance | ~1e11 | **lit + metric caveat** | **"cycles" is the wrong metric** — a-IGZO switching is effectively unbounded (imec 2T0C DRAM ≥1e11); real wear-out is bias-stress Vth-drift *lifetime* (time, temperature-accelerated), not a cycle count |
| M | cycle_life | electrostatic 1e3–1e8 / mechanical ~1e10 | **lit-grounded** | Goldsmith 2001 (charging-limited electrostatic), cold-switched contacts 1e10 (Lampen 2004), Si-fatigue cap 1e11 (Muhlstein 2001). Foglet-specific geometry **extrapolated** |

### Methodology & system-level

| Item | Trust | Note |
|------|-------|------|
| Monte-Carlo fab yield | sound | input-knob perturbation by PROCESS_SIGMA; audit-verified |
| Model-risk (epistemic) | sound | output-metric perturbation by phi `_uncertainty_pct`; audit-verified |
| Composite stack yield | **upper bound** | layers assumed to fail *independently*; correlated process steps would lower it |
| M = composite | **partial** | EM d33 → locomotion, E endurance → cycle cap are wired; full E/PM coupling is first-pass |
| `integration` (planar/encapsulated/nanostructured) | **lit-grounded, simplified** | the real endurance lever, but the model does **not** yet penalise its added FAB complexity/yield |
| Champions | **stochastic** | single robust-search outputs; ±a few % run-to-run |
| Thermal-budget co-integration (`tools/integration.py`) | **lit-grounded, estimates** | T_process for E/EM is the live champion anneal/dep temp; L/PM/M from literature. **T_survive values are materials-physics estimates, NOT in-house TGA/anneal-ladder data**; peak-temp only (no thermal-dose/expansion/interdiffusion). Result: only **2 of 120** build orders are viable (EM/E → L → PM → M); PM's ~250 °C ceiling pins it to the cold top |
| Device envelopes (`tools/devices.py`, `docs/DEVICES.md`) | **mixed, order-of-magnitude** | audited 2026-06-04 (`AUDIT_2026-06-04.md`). Thermal budgets are first-principles but use optimistic `h`/`dT` (ceilings). **Memory capacity is NOT firm** — see the plane-count row. **Logic clock corrected**: IGZO is ~10 MHz *measured* / ~0.2 GHz *projected* → ~400× Si gap (not 13×). Optical "matrix side" ≠ cascade depth. Order-of-magnitude product envelopes |
| E areal density / capacity (`devices.py`) | **speculative on planes** | demonstrated density ~1e10 bit/cm²/plane (FeFET); 1e12 (1F²) is a *lithographic ceiling*, not a cell density. **Plane counts 4/8/16 are an un-derived roadmap multiplier** — the thermal budget (`integration.py`) supports only ~2–4 monolithic E planes today, so high-plane capacities are not reconciled with co-integration |
| Area-yield / "watch first" (`devices.py`) | **heuristic, illustrative** | monolithic yield ~exp(−A·D₀·layers) with D₀=0.05/cm²/layer (optimistic, illustrative). The *relative* ordering (watch ≫ phone ≫ desktop) is robust and is the dominant reason to build the watch first; absolute yields are not a process figure. (Computed inline in `devices.py`, not via `stack_yield.py`) |

## What the audit corrected (don't trust pre-2026-06-03 numbers)

Stale figures that appear in older docs/ledger and were **wrong or over-stated**:
`EM d33 ≈ 16–18` (was low-biased → ~22), `PM FOM > 1700` (k was 85× too high →
FOM is no longer a discriminator), `M latch 551 mN` (shell-dielectric bug, 25×
inflated → ~0.28 mN air-gap), `PM endurance 1e7 base / cap 1e9` (over-optimistic →
1e5 base / 1e8 cap), `"Sb₂Se₃ out-endures GST"` (**false** — GST does 1e9–1e12;
Sb₂Se₃'s edge is *optical loss*, not cycles). See the audit doc for the full list
and the fix commits.

## How to regenerate / check

```bash
python3 tools/reliability.py --root . --model-risk   # fab-failure + endurance board
python3 tools/stack_yield.py  --root . --model-risk   # composite stack yield
python3 tools/loop_kernel_adapter.py --layer <L> --robust --model-risk --pareto
python3 tools/integration.py   --root .                # thermal-budget fab-order feasibility
python3 tools/devices.py       --root .                # per-device capability envelopes
python3 tools/testchip.py      --root .                # falsifiable single-layer test-chip specs
```
