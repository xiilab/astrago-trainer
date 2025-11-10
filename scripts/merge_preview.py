#!/usr/bin/env python3
"""
Local preview of how podTemplateOverrides merges with Runtime pod template.
Focus: initContainers merge by name (add new, merge/override existing env fields).

Usage:
  python3 tools/merge_preview.py \
      --runtime tensorflow/tensorflow-runtime.yaml \
      --trainjob tensorflow/tensorflow-trainjob-with-configmap.yaml

This script is a best-effort emulation for validation purposes and prints the
effective initContainers after applying overrides.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except Exception as e:
    print("[error] PyYAML is required. Install with: pip3 install pyyaml", file=sys.stderr)
    raise


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_runtime_podspec(runtime: Dict[str, Any]) -> Dict[str, Any]:
    # spec.template.spec.replicatedJobs[0].template.spec.template.spec
    try:
        return (
            runtime["spec"]["template"]["spec"]["replicatedJobs"][0]
            ["template"]["spec"]["template"]["spec"]
        )
    except Exception as e:
        raise KeyError("Unexpected runtime structure: spec.template.spec.replicatedJobs[0].template.spec.template.spec") from e


def get_trainjob_override_spec(trainjob: Dict[str, Any]) -> Dict[str, Any]:
    # spec.podTemplateOverrides[0].spec
    try:
        return trainjob["spec"]["podTemplateOverrides"][0]["spec"]
    except Exception as e:
        raise KeyError("Unexpected trainjob structure: spec.podTemplateOverrides[0].spec") from e


def merge_env_lists(base: List[Dict[str, Any]] | None, override: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    base = base or []
    override = override or []
    name_to_idx = {e.get("name"): i for i, e in enumerate(base) if isinstance(e, dict) and "name" in e}
    for item in override:
        if not isinstance(item, dict) or "name" not in item:
            base.append(item)
            continue
        n = item["name"]
        if n in name_to_idx:
            base[name_to_idx[n]] = item  # replace
        else:
            base.append(item)
    return base


def merge_init_containers(runtime_spec: Dict[str, Any], override_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_list: List[Dict[str, Any]] = list(runtime_spec.get("initContainers") or [])
    ov_list: List[Dict[str, Any]] = list(override_spec.get("initContainers") or [])

    base_idx = {c.get("name"): i for i, c in enumerate(base_list) if isinstance(c, dict) and "name" in c}
    for oc in ov_list:
        if not isinstance(oc, dict) or "name" not in oc:
            base_list.append(oc)
            continue
        name = oc["name"]
        if name in base_idx:
            # shallow merge + env merge
            idx = base_idx[name]
            merged = dict(base_list[idx])
            for k, v in oc.items():
                if k == "env":
                    merged["env"] = merge_env_lists(merged.get("env"), v)
                else:
                    merged[k] = v
            base_list[idx] = merged
        else:
            base_list.append(oc)
    return base_list


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--trainjob", required=True)
    args = ap.parse_args()

    runtime = load_yaml(args.runtime)
    trainjob = load_yaml(args.trainjob)
    runtime_spec = get_runtime_podspec(runtime)
    override_spec = get_trainjob_override_spec(trainjob)

    merged_init = merge_init_containers(runtime_spec, override_spec)

    print("=== Merged initContainers (preview) ===")
    print(yaml.safe_dump(merged_init, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()



