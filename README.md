<h1 align="center">Morphium Kernel</h1>

<p align="center">
  <em>A post-silicon material platform for reconfigurable computing.</em><br/>
  <sub>Layer contracts &middot; physics simulators &middot; cryptographically-verified champion recipes.</sub>
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

> Every champion in `artifacts/GOLDEN_IMAGE.json` is reproducible from `ledger/recipes.ndjson` via `tools/gatekeeper.py`. Nothing is hand-tuned — if the gatekeeper does not bless it, it is not a champion.

## The Stack

| Layer  | Function          | Material            | Key Metric                        |
| :----: | :---------------- | :------------------ | :-------------------------------- |
| **E**  | Logic / Memory    | `Hf0.5Zr0.5O2`      | Non-volatile, W-bit FTJ           |
| **EM** | Actuation         | `Sc0.38Al0.62N`     | Piezo $d_{33} \approx 18$ pC/N    |
| **PM** | Photonics         | `Sb2Se3:Ge:Cl`      | Phase-change FOM $> 1{,}700$      |
| **L**  | Oxide Logic       | `IGZO`              | Mobility $\mu > 10$ cm²/V·s       |
| **M**  | Modular / Foglet  | `HfO2:DLC`          | Electrostatic latch, 551 mN       |

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
│   └── stress_test.py
├── ledger/                # Immutable discovery history (append-only NDJSON)
├── artifacts/             # Blessed state — GOLDEN_IMAGE.json
├── config/                # phi calibration constants
├── papers/                # Master paper, recipes, cost analysis
├── docs/                  # Architecture, risk register, defense, metrology
├── evidence/              # Verified champion evidence per layer
├── hardware/              # Mask sets and latch designs (placeholders)
├── lab/                   # Bench scripts, notebooks, raw data (placeholders)
└── tests/
```

## Documentation

| Document | Purpose |
| :--- | :--- |
| [Architecture Freeze](docs/ARCHITECTURE_FREEZE.md)        | Locked design decisions for v1.0 |
| [Champions](docs/CHAMPIONS.md)                            | Verified state-of-the-art per layer |
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
