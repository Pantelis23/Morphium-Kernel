# Morphium Champions (v1.5 kernel)

**Regenerated 2026-06-03** from the current kernel + calibration (`config/phi.json`
v1.4), after the truthfulness audit. These are model-aware (process + simulator
uncertainty) robust-search champions — **simulation results, not lab-verified.**
The previous table was stale (v1.0, 2026-04-25) and mislabeled "Verified"; that
label is removed until physical measurements exist.

| Layer | Material | Headline metric | Fab-yield (process+model) | Notes |
|:---|:---|:---|:---|:---|
| **E** | `Hf0.49Zr0.49Al0.02O2` | Pr ≈ 17.6 µC/cm² | ~93% | 10 nm, calibrated ±25% |
| **EM** | `Sc0.34Al0.66N` | d33 ≈ 20.5 pC/N | ~98% | x_Sc≤0.38 cap; d33 recalibrated (audit M-6) |
| **PM** | `Sb2.5:Se4.2:Ge0.05:Cl0.11` | Δn ≈ 0.75, loss_k ≈ 8e-6 | ~100% | FOM huge (k≈real <1e-5); Δn gates |
| **L** | `IGZO` cation In0.63/Ga0.27/Zn0.10 | µ ≈ 21 cm²/Vs | ~88% | In-rich; **see caveat below** |
| **M** | `HfO2:DLC` foglet | latch ≈ 0.28 mN (air gap) | ~93% | composite, requires E/EM/PM |

**Composite M-stack yield** (M × E × EM × PM, model-aware, independent): **~76%**;
process-only **~99%**. See `tools/stack_yield.py`.

## Caveats (do not skip)

- **These are simulation outputs.** Every metric is model + literature-calibrated,
  not measured. The `phi.json` `_notes` per layer state the residual uncertainty
  and what in-house measurement would tighten it.
- **Layer L is In-rich (cation Zn = 0.10, the floor).** µ ≈ 21 is physically
  defensible for In-rich a-IGZO (lit 19–50 cm²/Vs) but sits *outside* the
  ~1:1:1-anchored ±40% calibration window — treat as an extrapolation. The model's
  µ≈13 calibration reference (cation In/Ga/Zn ≈ 0.49/0.46/0.05) is a *separate*
  device, not this champion (audit DOC-2).
- **M latch force** is the corrected air-gap value (audit C-1); the old 551 mN used
  the foglet shell's dielectric (k=25) for the gap — a bug. `cycle_life` is a
  placeholder constant, not modelled (audit DOC-4).
- **PM FOM** is now ~1e5 because loss_k ≈ real (<1e-5); FOM is therefore not a
  meaningful discriminator at this k — **Δn ≥ 0.30 is the binding PM gate**, not
  FOM. Earlier docs quoted FOM values of 81 / 795 / 1078 / 1625 at different k
  scales; ignore those (audit m-6).

Champions are re-derivable via `python3 tools/loop_kernel_adapter.py --layer <L>
--robust --model-risk` (stochastic; ±a few % run to run).
