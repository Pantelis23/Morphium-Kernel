#!/usr/bin/env python3
import argparse
import importlib.util
import json
import hashlib
import os
import sys
import datetime
from pathlib import Path
import yaml # Requires PyYAML

def utc_now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def canonicalize(obj, float_round=4):
    if isinstance(obj, float):
        return round(obj, float_round)
    if isinstance(obj, dict):
        return {k: canonicalize(v, float_round) for k, v in obj.items()}
    if isinstance(obj, list):
        return [canonicalize(v, float_round) for v in obj]
    return obj

def sha256_json(obj):
    # Canonical JSON string generation
    canon = canonicalize(obj)
    s = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def load_contract(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_layer_api(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def check_thresholds(metrics, promo):
    errors = []
    thresholds = promo.get("thresholds", {})
    for metric, rule in thresholds.items():
        if metric not in metrics:
            errors.append(f"missing:{metric}")
            continue
        val = metrics[metric]
        
        # Parse Min/Max
        if isinstance(rule, dict):
            if "min" in rule and val < float(rule["min"]):
                errors.append(f"{metric} {val} < {rule['min']}")
            if "max" in rule and val > float(rule["max"]):
                errors.append(f"{metric} {val} > {rule['max']}")
        else:
            # Assume scalar is min
            if val < float(rule):
                errors.append(f"{metric} {val} < {rule}")
                
    return len(errors) == 0, errors

def score_candidate(metrics, contract):
    score = 0.0
    for m in contract.get("metrics", []):
        name = m["name"]
        if name not in metrics: continue
        
        val = float(metrics[name])
        weight = float(m.get("weight", 1.0))
        target = m.get("target", 0.0)
        direction = m.get("direction", "maximize")
        
        if direction == "maximize":
            score += val * weight
        elif direction == "minimize":
            score -= val * weight
        elif direction == "target":
            dist = abs(val - target)
            score -= dist * weight
            
    return score

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default="MORPHIUM_KERNEL/ledger/recipes.ndjson")
    parser.add_argument("--kernel", default="MORPHIUM_KERNEL")
    parser.add_argument("--out", default="MORPHIUM_KERNEL/artifacts/GOLDEN_IMAGE.json")
    args = parser.parse_args()
    
    kernel_dir = Path(args.kernel)
    layers_dir = kernel_dir / "src/morphium_kernel/layers"
    ledger_path = Path(args.ledger)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load Layers
    contracts = {}
    apis = {}
    for layer_dir in layers_dir.iterdir():
        if not layer_dir.is_dir(): continue
        lid = layer_dir.name
        contracts[lid] = load_contract(layer_dir / "contract.yaml")
        apis[lid] = load_layer_api(layer_dir / "api.py")
        
    golden_candidates = {lid: [] for lid in contracts}
    report = {"hash_mismatches": [], "threshold_fails": [], "accepted": 0}
    
    # Process Ledger
    if not ledger_path.exists():
        print("No ledger found.")
        sys.exit(0)
        
    with open(ledger_path, "r") as f:
        for line in f:
            if not line.strip(): continue
            entry = json.loads(line)
            
            lid = entry["layer"]
            if lid not in apis: continue
            
            # 1. Re-Simulate (Verify Hash)
            # Our API.execute() returns {metrics, hash}
            # We need to construct the state passed to execute()
            # The ledger entry has 'formula', 'thickness', 'seed' mixed in top level
            # We need to reconstruct the "State" dict expected by execute()
            
            # ADAPTER LOGIC: Map Ledger Flat fields to API State
            # If 'state' key exists (L/M style), use it.
            # If not (E/EM/PM style), construct it from flat fields.
            
            sim_state = {}
            if "state" in entry and isinstance(entry["state"], dict):
                sim_state = entry["state"].copy()
            else:
                # Flat style (E, EM, PM)
                if "formula" in entry: sim_state["formula"] = entry["formula"]
                if "thickness_nm" in entry: sim_state["thickness_nm"] = entry["thickness_nm"]
                # Add other flat fields if necessary
            
            # Inject Seed
            if "seed" in entry:
                sim_state["seed"] = entry["seed"]
            
            api_result = apis[lid].execute(sim_state) # Re-run simulation
            
            recalc_hash = api_result["hash"]
            if recalc_hash != entry.get("hash"):
                report["hash_mismatches"].append({
                    "layer": lid, 
                    "expected": entry.get("hash"), 
                    "got": recalc_hash
                })
                print(f"HASH FAIL: {lid} {entry.get('hash')} vs {recalc_hash}")
                continue
                
            metrics = api_result.get("metrics", api_result.get("data")) # E/EM/PM used 'data', L/M used 'metrics'
            
            # 2. Check Promotion Thresholds
            promo = contracts[lid].get("promotion", {})
            passed, errs = check_thresholds(metrics, promo)
            
            if not passed:
                report["threshold_fails"].append({"layer": lid, "errors": errs})
                continue
                
            # 3. Score
            score = score_candidate(metrics, contracts[lid])
            
            candidate = {
                "layer": lid,
                "state": entry,
                "metrics": metrics,
                "score": score,
                "hash": recalc_hash
            }
            golden_candidates[lid].append(candidate)
            report["accepted"] += 1

    # Select Champions (Top 1)
    golden_image = {
        "generated_at": utc_now(),
        "layers": {}
    }
    
    for lid, cands in golden_candidates.items():
        if not cands: continue
        # Sort by Score Descending
        cands.sort(key=lambda x: x["score"], reverse=True)
        best = cands[0]
        golden_image["layers"][lid] = best
        print(f"LAYER {lid} CHAMPION: Score {best['score']:.2f}")

    with open(out_path, "w") as f:
        json.dump(golden_image, f, indent=2)
        
    print(f"Gatekeeper complete. {report['accepted']} accepted. Report saved.")

if __name__ == "__main__":
    main()
