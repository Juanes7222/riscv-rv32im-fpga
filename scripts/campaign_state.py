#!/usr/bin/env python3
"""Freshness bookkeeping for the experimental campaign.

Every measurement records the inputs it was made with (RTL fingerprint,
program hash) in results/campaign_state.json.  A stage whose recorded inputs
still match is skipped, so a repeated campaign only redoes what changed.
"""

import datetime
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

RESULTS = REPO_ROOT / "results"
STATE_FILE = RESULTS / "campaign_state.json"

# Artifacts generated from the loaded program: they change when another
# program is flashed and say nothing about the design.
GENERATED_RTL = {"mem_config.vh", "screen_writer_sc.sv",
                 "screen_writer_pipeline.sv"}
GENERATED_DIRS = {"__pycache__", "sim_build"}


def file_fingerprint(path: Path) -> str:
    """SHA-256 of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_files() -> list:
    files = [path for pattern in ("*.sv", "*.vh", "*.hex")
             for path in (REPO_ROOT / "rtl").rglob(pattern)
             if path.name not in GENERATED_RTL]
    for pattern in ("*/constraints.sdc", "*/setup.tcl", "*/build.tcl"):
        files += (REPO_ROOT / "synthesis").glob(pattern)
    return sorted(set(files))


def source_fingerprint() -> str:
    """Fingerprint of the hand-written RTL and its synthesis configuration."""
    digest = hashlib.sha256()
    for path in _source_files():
        digest.update(str(path.relative_to(REPO_ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()
                       and not GENERATED_DIRS.intersection(p.parts)
                       and p.suffix not in {".pyc", ".xml"}):
        digest.update(str(path.relative_to(REPO_ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def verification_fingerprint() -> str:
    """Fingerprint of the RTL and the cocotb suites it is verified with."""
    digest = hashlib.sha256(source_fingerprint().encode())
    digest.update(_tree_fingerprint(REPO_ROOT / "verification" / "cocotb").encode())
    return digest.hexdigest()


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def matches(state: dict, key: str, **inputs) -> bool:
    """True when the stage ran with exactly these inputs."""
    return state.get(key, {}).get("inputs") == inputs


def mark(state: dict, key: str, **inputs) -> None:
    state[key] = {
        "inputs": inputs,
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
