# State of Morphium

*A capstone synthesis (2026-06-04). What is real, what is speculative, and what it
would take to build the first device. Written on top of two adversarial audit rounds
([2026-06-03 materials](AUDIT_2026-06-03.md), [2026-06-04 system/device](AUDIT_2026-06-04.md)).*

---

## 1. What Morphium is

A **simulation platform** for a five-layer programmable-matter stack — one material
system that reconfigures into different devices under AI control:

| Layer | Material | Role |
|:--|:--|:--|
| **E** | HfZrO₂ ferroelectric | non-volatile memory / logic |
| **EM** | ScAlN piezo | actuation (the morphing engine) |
| **PM** | Sb₂Se₃ phase-change | nonvolatile photonics / optical weights |
| **L** | IGZO oxide TFT | back-end logic |
| **M** | HfO₂:DLC foglets | programmable matter (composite of E/EM/PM) |

The kernel simulates each layer's physics, calibrates to published literature via
additive `phi` offsets, and searches material compositions for champions. **It does
not prove physical correctness** — it proves reproducibility, threshold-compliance,
and literature-consistency *in simulation*. Every honesty caveat is tracked in
[`DATA_PROVENANCE.md`](DATA_PROVENANCE.md).

---

## 2. What is REAL (calibrated, literature-grounded)

These survived adversarial audit and match published data:

- **E — ferroelectric memory.** Pr ≈ 16–17 µC/cm², k ≈ 27, endurance ~1.2e11 cycles
  (Ru electrode). Non-volatile, zero *hold* power, ~10-yr retention at room
  temperature. This is Morphium's strongest, most-grounded layer.
- **L — IGZO logic.** Mobility ~44.5 cm²/Vs (In-rich, matches Lee/Cho 2018 anchor
  40–48); near-zero real off-current → seconds–hours DRAM retention, ~zero standby.
- **PM — phase-change photonics.** Δn ≈ 0.765 (pure Sb₂Se₃, multi-group anchor),
  ~6.7 dB/cm loss. The real edge is **low optical loss for nonvolatile weights**, not
  endurance (1e8, geometry-limited).
- **EM — piezo actuation.** d33 ~21–27 pC/N near x≈0.40 (sub-coercive ⇒ ~fatigue-free,
  ≥1e12 cycles). Reads conservative (~21) vs the lit plateau (~24–27).
- **The walls themselves.** The physical-limit envelopes ([`pressure_test.py`](../tools/pressure_test.py))
  and the thermal-budget co-integration logic ([`integration.py`](../tools/integration.py))
  are sound: only **2 of 120 build orders** are viable, PM's ~250 °C ceiling pins it to
  the cold top, and the binding fab risk is HZO surviving the ScAlN step.

---

## 3. What is SPECULATIVE (use with caution)

The 2026-06-04 audit flagged these — now labeled honestly everywhere:

- **Memory capacity at scale.** Single-plane demonstrated density ~1e10 bit/cm²; the
  1e12 (1 Tbit/cm²) figure is a *1F² lithographic ceiling*, not a cell density. Device
  capacities depend on a **speculative plane count (4/8/16)** that the thermal budget
  does not yet justify (~2–4 planes feasible). Read all capacities as order-of-magnitude.
- **Logic throughput.** IGZO TFT logic is ~**10 MHz measured** (0.2 GHz is an aggressive
  projection) — ~400× slower than Si. Morphium is *never* scalar-fast.
- **M foglet layer.** A first-pass composite; locomotion/latch/adhesion models are
  partly heuristic (audited and fixed in round 1, but not literature-calibrated like E/L).
- **Optical compute as a MAC engine.** PM stores nonvolatile weights at zero hold
  power; the *matrix dimension* is modest (tens, not ~900) and the MAC system has static
  power (lasers/detectors/ADC). Good for weight storage, not a free light-speed computer.
- **Monolithic yield.** Defect-limited and area-driven; only the *relative* ordering
  (watch ≫ phone ≫ desktop) is robust. Absolute yields are illustrative.

---

## 4. The system-level walls (these decide everything)

Material chemistry is mostly maxed out; the remaining limits are at the system level:

1. **Co-integration thermal budget.** Build hottest-first; PM (Sb₂Se₃, ~250 °C) forces
   the order **EM → E → L → PM → M**. Only ~2–4 E planes survive the cumulative anneal.
2. **Monolithic yield ~ exp(−area).** A desktop-area slab is un-yieldable (~0); even a
   watch is ~1.8% single-die → everything larger than a watch **must be tiled**.
3. **Logic clock ~400× below Si.** Forces every Morphium device into a
   memory-centric / parallel / compute-in-memory role, never single-thread.
4. **Heat (only when folded).** Thin face-cooled slabs shed heat fine; the 1/r "cooks
   itself" wall returns only if you fold a device into a brick.

---

## 5. Device verdicts

(Full detail + numbers in [`DEVICES.md`](DEVICES.md).)

- **Watch — build this first.** ~80 GB NV store, ~10 MHz logic (sufficient), crisp
  haptics, reflective display. The *only* form factor with workable single-die yield.
  Binding wall: **battery**, not heat. It exercises all five layers at the cheapest area.
- **Phone.** ~1 TB NV memory, photonic interconnect; needs tiling + a small Si companion
  core for the UI thread. Binding wall: thermal + clock + yield.
- **Desktop.** A **tiled compute-in-memory + optical-AI accelerator**, ~18 TB NV memory.
  Heat is solved by active cooling; the wall is clock + yield. **Not a Ryzen** — it wins
  parallel/memory-bound/inference, loses every serial benchmark.

---

## 6. What it would take to actually build the watch

The concrete near-term path, with the unknowns that must be retired first:

| Step | What | Open unknown / validation needed |
|:--|:--|:--|
| 1 | **Single-layer test chips** (E, L, EM, PM each standalone) | confirm champion metrics in-house (Hall µ, P-E loops, d33, ellipsometry) vs the simulated values |
| 2 | **EM→E thermal-ladder** | does finished HZO survive the 490 °C ScAlN step? (the +110 K margin, the #1 fab risk) |
| 3 | **PM survival anneal** | confirm Sb₂Se₃'s real survival ceiling (~250–300 °C?) — the binding co-integration wall |
| 4 | **2-layer monolithic integration** (E+L) | yield at watch area; cumulative-anneal effect on E plane count |
| 5 | **PM-under-M optical path** | can M be made optically sparse/transparent over the display aperture? (currently unmodeled) |
| 6 | **Reconfiguration demo** | M latch + PM set/reset cycling at a real granularity; energy/time budget |

None of these needs the full 5-layer stack to start — steps 1–3 are independent and
de-risk the whole program. **The simulation's job from here is to predict each of these
measurements**, so the first silicon either confirms or falsifies a specific number.

---

## 7. Honest go / no-go

**Go signal:** Morphium's material edges are real and grounded — non-volatile memory,
low-loss optical weight storage, fatigue-free piezo. The co-integration path exists
(a unique viable build order) and the first de-risking experiments are cheap and
independent.

**Hard truths the program must own:** it is **not a general-purpose computer** (logic
is ~400× slower than Si); large devices **must be tiled** (monolithic yield); and
high memory capacity depends on a **plane-count assumption not yet reconciled with the
thermal budget**. The vision ("talk to it, it becomes anything") is bounded by heat,
yield, clock, and reconfiguration energy — all real, all quantified here.

**Recommendation:** build the **watch** demonstrator, and run steps 1–3 in parallel
to validate the simulation against silicon. Everything else follows from whether those
numbers hold.
