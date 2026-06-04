# Morphium device envelopes — watch, phone, desktop

The five-layer stack (E/EM/PM/L/M) is one material system that reconfigures into
different products. This page specs three of them and names the binding wall for
each. Every number is **derived** from champion material metrics + the physical
walls ([`pressure_test.py`](../tools/pressure_test.py)), not asserted — regenerate:

```bash
python3 tools/devices.py          # full report
python3 tools/devices.py --json   # machine-readable
```

> **Honesty (adversarially audited 2026-06-04 — see [`AUDIT_2026-06-04.md`](AUDIT_2026-06-04.md)).**
> An earlier version of this page was optimistic by orders of magnitude on two axes;
> the corrected numbers are below. Memory capacity is **order-of-magnitude, not firm**:
> it is dominated by an un-derived *plane-count* assumption (4/8/16) that the thermal
> budget does not yet justify. Logic throughput is the **soft axis** — IGZO TFT logic
> is ~10 MHz *measured* (0.2 GHz is a scaled *projection*), so it is ~**400×** slower
> than Si, not 13×. Thermal `h`/`dT` are optimistic ceilings. These are
> order-of-magnitude product envelopes, not a datasheet. See
> [`DATA_PROVENANCE.md`](DATA_PROVENANCE.md).

## At a glance

| Device | Face | Cooling | Heat (ceiling) | NV memory (demonstrated) | Clock gap vs Si | Monolithic yield | Binding wall |
|--------|------|---------|----------------|--------------------------|-----------------|------------------|--------------|
| **Watch** | 4×4 cm | passive | ~5 W | **~80 GB** (8 TB ceiling) | ~400× | ~1.8 % | **battery energy** |
| **Phone** | 15×7 cm | passive | ~25 W | **~1 TB** (105 TB ceiling) | ~400× | ~4e-10 % | **thermal + clock + yield** |
| **Desktop** | 30×30 cm | active | ~1.2 kW* | **~18 TB** (1.8 PB ceiling) | ~400× | ~1e-96 % | **clock + yield** (heat solved) |

\* optimistic; a realistic bare-slab forced-air figure is ~300–600 W.

The common thread: Morphium's standout is **non-volatile memory** (E, 10-yr
retention at room temperature, zero *hold* power) and **nonvolatile photonic
weights** (PM optical compute, zero static hold power). Its weakness is **scalar
logic speed** (IGZO TFT ~10 MHz measured). So every Morphium device is
memory-centric and parallel, never single-thread-fast.

### Two corrections worth stating plainly (from the audit)

- **Memory density.** 1 Tbit/cm² is the *1F² lithographic ceiling* at the ~10 nm
  ferroelectric scaling limit, **not** an achievable cell density. Demonstrated
  FeFET/FeRAM is ~1e10 bit/cm²/plane. The headline capacities above use the
  demonstrated figure; the "ceiling" column is the theoretical roadmap. And the
  **plane counts (4/8/16) are speculative** — the thermal budget
  ([`integration.py`](../tools/integration.py)) supports only ~2–4 co-integrated E
  planes today, so high-capacity numbers are not yet reconciled with co-integration.
- **Logic clock.** Real a-IGZO logic runs at ~1–10 MHz (large geometry); 0.2 GHz is
  an *aggressive scaled projection*. The honest gap to 4 GHz Si is ~400× (measured),
  ~20× (projected) — not 13×. This is *why* "desktop computer" must be read as
  *accelerator*, not Ryzen.

### Geometry note (why heat isn't the wall here)

These devices are thin **slabs**, cooled through their two big faces, so the heat
budget scales as ~1/thickness — the *thinner* phone sheds more per cm³ than the
*thicker* watch, and all three shed fine. (`h`/`dT` are optimistic; read budgets as
ceilings.) The pressure-test "an umbrella-sized brick cooks itself" 1/r wall — which
models each object as a worst-case **sphere** — only returns if you *fold* a device
into a cube. Thin-and-spread beats small-and-stacked for heat.

## Watch — *build this first*

Wearable: sensing, haptics, reflective/ambient-light display, always-on.
- **~80 GB** non-volatile store, **zero hold power** (E is non-volatile → no refresh).
- **~10 MHz** IGZO logic — *sufficient* for a watch, not a liability.
- **~539 mN** EM blocked force → crisp haptics; M foglets → a morphing band/case.
- **Binding wall: battery energy, not heat.** All-day life on a ~300 mWh cell caps
  average draw to tens of mW — exactly the regime low-clock IGZO + non-volatile E
  was built for.

**Why first — now computed, not asserted.** Monolithic yield falls steeply with
area (defects ~ exp(−area·D₀·layers)): **watch ~1.8 % ≫ phone ~4e-10 % ≫ desktop
~1e-96 %**. The desktop is *un-yieldable* as a single slab — it must be tiled from
small dies; the watch is the only form factor with a workable single-die yield
(still modest → wants redundancy/tiling). That, plus lowest compute demand and
trivial thermals, makes it the cheapest way to exercise all five layers and de-risk
co-integration ([`integration.py`](../tools/integration.py)) and reconfiguration.

> **Display caveat (audit).** PM sits second-from-top in the only viable build order
> (under M). Using PM for the watch's reflective display therefore requires the M
> foglet layer to be **optically sparse/transparent over the display aperture** —
> this is currently *unmodeled* and is a real integration assumption, not a free lunch.

## Phone

Handset: display, mixed compute, very large NV memory, haptics.
- **~1 TB** non-volatile memory on one stack; PM photonic interconnect between blocks.
- **Binding wall: sustained thermal + clock + yield.** The passive budget is real but
  phones throttle under load; heavy apps hit the ~400× IGZO↔Si clock gap; and at
  105 cm² the monolithic yield is effectively zero, so it must be **tiled**. The phone
  wins on memory and photonic bandwidth, not peak single-thread — pair it with a small
  Si companion core for the latency-critical UI thread.

## Desktop

Stationary: a memory-centric + optical-AI accelerator — **not a scalar CPU**.
- **~18 TB** non-volatile memory; active cooling (optimistically ~1 kW, realistically
  ~300–600 W bare-slab) takes **thermal off the table** at desktop scale.
- **Binding wall: logic clock + monolithic yield.** With heat solved, the ~400×
  clock gap and the ~0 single-slab yield are the whole story — a Morphium "desktop"
  is a **tiled compute-in-memory + optical-AI machine** that out-throughputs a CPU on
  *parallel*, memory-bound, and inference workloads while losing every *serial*
  benchmark. It complements a conventional PC; it does not replace its CPU.

### Photonic compute — the honest framing

PM stores **nonvolatile optical weights** (write once, hold at **zero static
power**). The champion cascade depth (~897) is a **propagation/SNR limit, not a MAC
matrix dimension** — a coherent-mesh matrix side is ≤ ~448 under intrinsic loss only,
and far smaller (tens) once realistic per-modulator insertion loss is included. The
*compute* path still has nonzero static power (lasers/detectors/ADC) and is not
end-to-end "light speed"; the zero-power claim applies to **weight hold**, not the
whole MAC system.

## The honest one-liner

Morphium makes a strong **watch** (build it first — it's the only thing that yields),
a memory-and-photonics phone that needs tiling and a Si companion core, and a
**desktop-class AI/memory accelerator** that is emphatically *not a Ryzen*. The
material edges are real (non-volatile memory, optical weight storage); the
system-level limits (logic clock, monolithic yield, plane-count vs thermal budget)
are equally real and now stated plainly.
