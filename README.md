<h1 align="center">Morphium Kernel</h1>

<p align="center">
  <em>A post-silicon material platform for reconfigurable computing.</em><br/>
  <sub>Layer contracts &middot; physics simulators &middot; reproducible, literature-calibrated champion recipes (simulation).</sub>
</p>

<p align="center">
  <a href="LICENSE"><img alt="Code license" src="https://img.shields.io/badge/Code-MIT-blue?style=flat-square"></a>
  <a href="#license"><img alt="Data license" src="https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey?style=flat-square"></a>
  <a href="docs/ARCHITECTURE_FREEZE.md"><img alt="Status" src="https://img.shields.io/badge/Status-TRL%204%20%C2%B7%20Design%20Frozen-success?style=flat-square"></a>
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white"></a>
  <a href="artifacts/GOLDEN_IMAGE.json"><img alt="Golden Image" src="https://img.shields.io/badge/Golden%20Image-verified-2ea44f?style=flat-square"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#the-stack">The Stack</a> &middot;
  <a href="#how-it-works">How It Works</a> &middot;
  <a href="#documentation">Docs</a> &middot;
  <a href="#citation">Cite</a>
</p>

---

## Overview

**Morphium** is a unified material platform that replaces the fragmented stack of modern computing (Silicon Logic + DRAM + Flash + PCB + Display + Case) with a single monolithic, reconfigurable substrate. This repository ships the **executable artifacts** behind that claim: layer contracts, physics simulators, an immutable discovery ledger, and a cryptographic gatekeeper that verifies the champion materials against the kernel.

> Every champion in `artifacts/GOLDEN_IMAGE.json` is reproducible from `ledger/recipes.ndjson` via `tools/gatekeeper.py`. Champions are GA/Monte-Carlo *search* outputs — not hand-picked — but the underlying physics models are **calibrated to published literature** (the calibration constants in `config/phi.json` are literature-anchored). The gatekeeper guarantees *reproducibility and threshold-compliance in simulation*, **not** physical correctness. See [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md).

> 📋 **Start here:** [`docs/STATE_OF_MORPHIUM.md`](docs/STATE_OF_MORPHIUM.md) — the capstone synthesis: what's real, what's speculative, the system-level walls, the device verdicts, and what it would take to build the first one. Backed by two adversarial audit rounds ([materials](docs/AUDIT_2026-06-03.md), [system/device](docs/AUDIT_2026-06-04.md)).

## The Stack

| Layer  | Function          | Material                  | Key Metric (simulation, lit-calibrated) |
| :----: | :---------------- | :------------------------ | :-------------------------------------- |
| **E**  | Logic / Memory    | `Hf0.49Zr0.49Al0.02O2`    | Pr $\approx 17.6$ µC/cm² (FTJ)          |
| **EM** | Actuation         | `Sc0.34Al0.66N`           | Piezo $d_{33} \approx 22$ pC/N          |
| **PM** | Photonics         | `Sb2Se3:Ge:Cl`            | Phase-change $\Delta n \approx 0.75$, low-loss |
| **L**  | Oxide Logic       | `IGZO` (In-rich)          | Mobility $\mu \approx 21$ cm²/V·s        |
| **M**  | Modular / Foglet  | `HfO2:DLC` (composite)    | Foglet; mechanical latch (needs E/EM/PM) |

> **Status & data honesty.** These are **simulation** results from literature-calibrated physics models — **not lab measurements.** "Verified"/"blessed" here means the gatekeeper *reproducibly* re-derives a champion from the ledger and it passes the contract thresholds — a **reproducibility** guarantee, not a physical one. Per-layer trust varies (calibrated → literature-grounded → heuristic); see [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md) for the trust level behind **every** number, and [`docs/AUDIT_2026-06-03.md`](docs/AUDIT_2026-06-03.md) for the adversarial audit that corrected several of them.

See [`docs/CHAMPIONS.md`](docs/CHAMPIONS.md) for the full champion table and [`papers/MORPHIUM_MASTER_PAPER.md`](papers/MORPHIUM_MASTER_PAPER.md) for the full physics write-up.

## Quick Start

### Requirements

- Python 3.10+
- `PyYAML` (only runtime dependency)

```bash
pip install pyyaml
```

### Verify the Champions

Run the **Gatekeeper** to cryptographically re-derive `GOLDEN_IMAGE.json` from the discovery ledger and verify it against the simulation kernel.

```bash
python3 tools/gatekeeper.py \
    --ledger ledger/recipes.ndjson \
    --out    artifacts/GOLDEN_IMAGE.json
```

### Run a Search

Use the Loop Adapter to discover optimised compositions for any layer.

```bash
python3 tools/loop_kernel_adapter.py --layer L --budget 100
```

### Stress-Test a Champion

```bash
python3 tools/stress_test.py --layer EM
```

### Check Monolithic-Integration Feasibility

Can the five layers be co-fabricated into one stack, and in what order? The
descending-thermal-budget model reports the viable fab sequences and the binding
constraint (only **2 of 120** orderings survive; PM's ~250 °C ceiling pins it on top).

```bash
python3 tools/integration.py
```

### See What Devices the Stack Becomes

Map the same stack onto a watch, phone, and desktop — derived capability and the
binding wall for each (watch = battery, phone = thermal+clock, desktop = logic clock).
Full write-up in [`docs/DEVICES.md`](docs/DEVICES.md).

```bash
python3 tools/devices.py
```

### Get the Falsifiable Test-Chip Specs

Turn each champion into a single-layer test chip the simulation **commits to
predicting** — recipe, process temp, predicted metrics with ± bands, metrology
method, and the falsification criterion. This is the bridge to silicon (step 1 of
[`docs/STATE_OF_MORPHIUM.md`](docs/STATE_OF_MORPHIUM.md)).

```bash
python3 tools/testchip.py            # all layers
python3 tools/testchip.py --layer E  # one layer
```

## Repository Structure

```text
.
├── src/morphium_kernel/   # Core kernel: simulator + per-layer contracts and APIs
│   ├── kernel.py
│   └── layers/{E,EM,PM,L,M}/
├── tools/                 # Discovery loop, gatekeeper, simulators, analysis
│   ├── gatekeeper.py
│   ├── loop_kernel_adapter.py
│   ├── multi_radix_sim.py
│   ├── healing_sim.py
│   ├── sensitivity_analysis.py
│   ├── integration.py      # thermal-budget co-integration / fab-order feasibility
│   ├── devices.py          # per-device (watch/phone/desktop) capability envelopes
│   ├── testchip.py         # single-layer falsifiable test-chip specs (predicted metric + band)
│   └── stress_test.py
├── ledger/                # Immutable discovery history (append-only NDJSON)
├── artifacts/             # Blessed state — GOLDEN_IMAGE.json
├── config/                # phi calibration constants
├── papers/                # Master paper, recipes, cost analysis
├── docs/                  # Architecture, risk register, defense, metrology
├── evidence/              # Champion evidence per layer (simulation)
├── hardware/              # Mask sets and latch designs (placeholders)
├── lab/                   # Bench scripts, notebooks, raw data (placeholders)
└── tests/
```

## Documentation

| Document | Purpose |
| :--- | :--- |
| [Architecture Freeze](docs/ARCHITECTURE_FREEZE.md)        | Locked design decisions for v1.0 |
| [Champions](docs/CHAMPIONS.md)                            | Current state-of-the-art per layer (simulation) |
| [**Data Provenance**](docs/DATA_PROVENANCE.md)            | **Trust level + source behind every number** |
| [Truthfulness Audit](docs/AUDIT_2026-06-03.md)           | Adversarial audit (2026-06-03) and its corrections |
| [Risk Register](docs/RISK_REGISTER.md)                    | Known risks and mitigations |
| [Fabrication Plan](docs/FABRICATION_PLAN.md)              | Path from kernel to silicon |
| [Metrology Plan](docs/METROLOGY_PLAN.md)                  | Measurement protocols |
| [Final Defense](docs/FINAL_DEFENSE.md)                    | Argument against red-team objections |
| [Master Paper](papers/MORPHIUM_MASTER_PAPER.md)           | Full project write-up |

## How It Works

```
┌──────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  loop_kernel_    │ ──▶ │   morphium_      │ ──▶ │  ledger/            │
│  adapter.py      │     │   kernel (sim)   │     │  recipes.ndjson     │
│  (GA + MC)       │     │                  │     │  (append-only)      │
└──────────────────┘     └──────────────────┘     └──────────┬──────────┘
                                                             │
                                                             ▼
                                                  ┌─────────────────────┐
                                                  │  gatekeeper.py      │
                                                  │  (canonical hash +  │
                                                  │  threshold check)   │
                                                  └──────────┬──────────┘
                                                             │
                                                             ▼
                                                  ┌─────────────────────┐
                                                  │  artifacts/         │
                                                  │  GOLDEN_IMAGE.json  │
                                                  └─────────────────────┘
```

1. **Search.** The Loop Adapter explores composition space with a Genetic Algorithm + Monte Carlo yield analysis.
2. **Record.** Every trial is appended — never edited — to the NDJSON ledger.
3. **Bless.** The Gatekeeper canonicalises each top trial, hashes it, checks contract thresholds, and emits the Golden Image.
4. **Verify.** Anyone can re-run the Gatekeeper and reproduce the same hashes bit-for-bit.

## Contributing

Contributions that extend the kernel, add new layer contracts, or improve calibration are welcome.

1. Fork and create a feature branch.
2. Add or modify layer APIs under `src/morphium_kernel/layers/<LAYER>/` with an updated `contract.yaml`.
3. Run the gatekeeper locally and confirm the Golden Image still verifies.
4. Open a PR describing the contract change, the new champion (if any), and the calibration evidence.

Please do not commit edits to `ledger/*.ndjson` — append only, via the loop adapter.

## License

- **Code** — [MIT](LICENSE)
- **Data** (recipes, ledgers, golden image) — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

## Citation

If you reference this work, please cite the master paper:

```bibtex
@misc{morphium_kernel_2026,
  title  = {Morphium Kernel: A Reconfigurable Material Stack},
  author = {Pantelis Christou},
  year   = {2026},
  url    = {https://github.com/Pantelis23/Morphium-Kernel}
}
```
