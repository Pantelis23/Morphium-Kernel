"""
Kernel Client (SDK)
Unified interface for interacting with Morphium Kernel layers.
Handles validation, simulation, caching, and ledger commit.
"""
import json
import hashlib
import importlib.util
import yaml
from pathlib import Path
from datetime import datetime, timezone

# Helper for loading modules dynamically
def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class KernelClient:
    def __init__(self, project_root="MORPHIUM_KERNEL"):
        self.root = Path(project_root)

        # Code Paths (Source)
        self.layers_dir = self.root / "src/morphium_kernel/layers"

        # Data Paths (Ledger)
        self.ledger_dir = self.root / "ledger"
        self.trials_path = self.ledger_dir / "trials.ndjson"
        self.recipes_path = self.ledger_dir / "recipes.ndjson"

        # Load Registry
        self.contracts = {}
        self.apis = {}
        if not self.layers_dir.exists():
             print(f"Warning: Layers dir not found at {self.layers_dir}")

        for p in self.layers_dir.iterdir():
            if p.is_dir() and (p / "contract.yaml").exists():
                lid = p.name
                with open(p / "contract.yaml") as f:
                    self.contracts[lid] = yaml.safe_load(f)
                self.apis[lid] = load_module(p / "api.py")

        # Load φ calibration offsets (sim-to-real correction).
        # All zeros by default (no calibration). Updated externally via GP
        # when real lab measurements arrive.
        phi_path = self.root / "config" / "phi.json"
        self._phi: dict = {}
        if phi_path.exists():
            with open(phi_path) as f:
                raw = json.load(f)
            # Extract per-layer dicts, skip _description/_format/_version keys
            for key, val in raw.items():
                if not key.startswith("_") and isinstance(val, dict):
                    # Load from 'offsets' sub-dict if present (v1.2+ schema);
                    # fall back to flat layer dict for backwards compatibility.
                    raw_offsets = val.get("offsets", None)
                    if raw_offsets is not None:
                        self._phi[key] = {
                            k: v for k, v in raw_offsets.items()
                            if isinstance(v, (int, float))
                        }
                    else:
                        self._phi[key] = {
                            k: v for k, v in val.items()
                            if isinstance(v, (int, float))
                        }

    def contract(self, layer):
        return self.contracts.get(layer)

    def validate(self, layer, state):
        contract = self.contracts.get(layer)
        if not contract: return False, ["Unknown layer"]
        
        # Basic Schema Check (Recursive)
        # TODO: Full JSON schema validation
        # For now, check if 'state' matches top-level contract keys if they exist
        schema = contract.get("state_schema", {})
        errors = []
        
        # Very basic check: numeric bounds
        if layer == "L" and "materials" in state:
            comp = state["materials"].get("channel_composition", {})
            if abs(sum(comp.values()) - 1.0) > 0.01:
                errors.append("Composition sum != 1.0")
                
        return len(errors) == 0, errors

    def simulate(self, layer, state, seed=42):
        if layer not in self.apis:
            raise ValueError(f"Unknown layer: {layer}")

        sim_state = state.copy()
        sim_state["seed"] = seed

        result = self.apis[layer].execute(sim_state)

        # Apply φ calibration offsets to metrics (additive correction).
        # No-op when all offsets are 0.0 (default).
        # Note: L/PM/EM use result["metrics"]; E uses result["data"].
        phi_layer = self._phi.get(layer, {})
        metrics_key = "metrics" if "metrics" in result else "data"
        if phi_layer and metrics_key in result and isinstance(result[metrics_key], dict):
            for metric, offset in phi_layer.items():
                if offset != 0.0 and metric in result[metrics_key]:
                    result[metrics_key][metric] = result[metrics_key][metric] + offset
            if any(v != 0.0 for v in phi_layer.values()):
                result["phi_applied"] = phi_layer
                # Recalculate derived metric fom = delta_n / loss_k after phi correction.
                # delta_n and/or loss_k may have changed; fom was computed pre-phi inside execute().
                m = result[metrics_key]
                if "fom" in m and "delta_n" in m and "loss_k" in m and m["loss_k"] > 0:
                    m["fom"] = round(m["delta_n"] / m["loss_k"], 2)

        return result

    def score(self, layer, metrics):
        contract = self.contracts[layer]
        score = 0.0
        for m in contract.get("metrics", []):
            name = m.get("name")
            if name not in metrics: continue
            val = float(metrics[name])
            weight = float(m.get("weight", 1.0))
            target = m.get("target", 0.0)
            direction = m.get("direction", "maximize")
            
            if direction == "maximize": score += val * weight
            elif direction == "minimize": score -= val * weight
            elif direction == "target": score -= abs(val - target) * weight
        return score

    def passes_thresholds(self, layer, metrics):
        contract = self.contracts[layer]
        promo = contract.get("promotion", {}).get("thresholds", {})
        for k, rule in promo.items():
            if k not in metrics: return False
            val = metrics[k]
            if isinstance(rule, dict):
                if "min" in rule and val < float(rule["min"]): return False
                if "max" in rule and val > float(rule["max"]): return False
            else:
                if val < float(rule): return False
        return True

    def commit_trial(self, entry):
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        # Inject sim_model_version from layer API if not already present
        if "sim_model_version" not in entry:
            layer = entry.get("layer")
            if layer and layer in self.apis:
                api_mod = self.apis[layer]
                entry["sim_model_version"] = getattr(api_mod, "SIM_MODEL_VERSION", "unknown")
        with open(self.trials_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def commit_recipe(self, entry):
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        entry["status"] = "CANDIDATE"
        # Inject sim_model_version from layer API if not already present
        if "sim_model_version" not in entry:
            layer = entry.get("layer")
            if layer and layer in self.apis:
                api_mod = self.apis[layer]
                entry["sim_model_version"] = getattr(api_mod, "SIM_MODEL_VERSION", "unknown")
        with open(self.recipes_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
