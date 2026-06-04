# Morphium device envelopes — watch, phone, desktop

The five-layer stack (E/EM/PM/L/M) is one material system that reconfigures into
different products. This page specs three of them and names the binding wall for
each. Every number is **derived** from the champion material metrics + the
physical walls (see [`pressure_test.py`](../tools/pressure_test.py)), not asserted —
regenerate with:

```bash
python3 tools/devices.py          # full report
python3 tools/devices.py --json   # machine-readable
```

> **Honesty.** Memory capacity and thermal budgets are first-principles and firm.
> Logic **throughput** is the soft axis: IGZO TFT logic is low-clock (~0.1–1 GHz,
> assumed 0.3), so the Si clock gap (~13×) is the honest reason Morphium is not a
> scalar CPU. Foglet counts are granularity-floor maxima, not built designs. These
> are order-of-magnitude product envelopes, not a datasheet. See
> [`DATA_PROVENANCE.md`](DATA_PROVENANCE.md).

## At a glance

| Device | Face | Cooling | Heat budget | NV memory | Clock gap vs Si | Binding wall |
|--------|------|---------|-------------|-----------|-----------------|--------------|
| **Watch** | 4×4 cm | passive | 5 W (267 mW/cm³) | ~8 TB | ~13× | **battery energy** |
| **Phone** | 15×7 cm | passive | 25 W (292 mW/cm³) | ~105 TB | ~13× | **sustained thermal + clock** |
| **Desktop** | 30×30 cm | active | 1152 W (1280 mW/cm³) | ~1.8 PB | ~13× | **logic clock** (heat is solved) |

The common thread: Morphium's standout is **non-volatile memory density** (E at
~1 Tbit/cm², 10-yr retention, zero refresh power) and **nonvolatile photonic
compute** (PM optical weights, light-speed MACs, ~897 cascade depth). Its weakness
is **scalar logic speed** (IGZO TFT clock). So every Morphium device is
memory-centric and parallel, never single-thread-fast.

### Geometry note (why heat isn't the wall here)

These devices are thin **slabs**, cooled through their two big faces, so the heat
budget scales as ~1/thickness — the *thinner* phone actually sheds more per cm³
than the *thicker* watch, and all three shed fine. The pressure-test "an
umbrella-sized brick cooks itself" 1/r wall only returns if you **fold** a device
into a cube. Thin-and-spread beats small-and-stacked for heat.

## Watch — *build this first*

Wearable: sensing, haptics, reflective/ambient-light display, always-on.
- **~8 TB** non-volatile store, **zero standby power** (E is non-volatile → no refresh).
- **~0.3 GHz** IGZO logic — *sufficient* for a watch, not a liability.
- **~539 mN** EM blocked force → crisp haptics; M foglets → a morphing band/case.
- PM modulates ambient light for an always-on reflective display (no backlight power).
- **Binding wall: battery energy, not heat.** All-day life on a ~300 mWh cell caps
  average draw to tens of mW — which is exactly the regime low-clock IGZO +
  non-volatile E was built for. It never approaches its thermal ceiling.

**Why first:** smallest face area → **highest composite yield** (yield ~ exp(−area);
see [`stack_yield.py`](../tools/stack_yield.py)); lowest absolute compute demand;
thermally trivial; yet it still exercises **all five layers** (E store, L logic,
PM display, EM haptics, M morphing). It de-risks the hard parts —
co-integration (see [`integration.py`](../tools/integration.py)) and
reconfiguration — at the cheapest possible area and cost.

## Phone

Handset: display, mixed compute, very large NV memory, haptics.
- **~105 TB** non-volatile memory on one stack; PM photonic interconnect between blocks.
- **Binding wall: sustained thermal + clock.** The 25 W passive budget is real but
  phones throttle under load, and heavy apps hit the ~13× IGZO↔Si clock gap. The
  phone wins on **memory and photonic bandwidth**, not on peak single-thread —
  pair it with a small Si companion core for the latency-critical UI thread.

## Desktop

Stationary: a memory-centric + optical-AI accelerator — **not a scalar CPU**.
- **~1.8 PB** non-volatile memory; active cooling lifts the budget past **1 kW**, so
  **thermal is solved** at desktop scale.
- **Binding wall: logic clock.** With heat off the table, the ~13× clock gap is the
  whole story — IGZO TFT logic cannot do GHz scalar work. The honest reframe: a
  Morphium "desktop" is a **compute-in-memory + optical-AI machine** — petabytes of
  non-volatile weights read at light speed through PM cascades — that vastly
  out-throughputs a CPU on *parallel* memory-bound and inference workloads while
  losing every *serial* benchmark. It complements a conventional PC; it doesn't
  replace its CPU.

## The honest one-liner

Morphium makes a brilliant **watch**, a memory-and-photonics-strong **phone**, and
a **desktop-class AI/memory accelerator** — but its low-clock logic means "desktop
computer" should be read as *accelerator*, not *Ryzen*. Build the watch first.
