#!/usr/bin/env python3
"""Freeze synthesis inputs and seal the reports of one new replica."""

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from campaign_state import FINGERPRINT_VERSION, source_fingerprint, _source_files

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(directory, arch, seed, elf):
    """Refuse overwrites and archive the actual sources and memory images."""
    if directory.exists():
        raise SystemExit(f"Replica already exists: {directory}; choose a new RESULTS_DIR")
    paths = _source_files() + [
        ROOT / "rtl/shared/mem_config.vh", elf.resolve(),
        ROOT / "build/imem.mem", ROOT / "build/dmem.mem",
        ROOT / "synthesis" / arch / "screen.mif",
    ]
    project = ROOT / "synthesis" / arch / f"rv32im_{arch}"
    configuration = [project.with_suffix(suffix) for suffix in (".qpf", ".qsf")]
    for path in paths + configuration:
        if not path.is_file():
            raise SystemExit(f"Missing synthesis input: {path}")
    version = subprocess.check_output(["quartus_sh.exe", "--version"], text=True)
    directory.mkdir(parents=True)
    manifest = {
        "schema": 1, "status": "prepared", "architecture": arch, "seed": seed,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "fingerprint_version": FINGERPRINT_VERSION,
        "fingerprint": source_fingerprint(), "quartus_version": version.strip(),
        "tohost_addr": int(os.environ.get("TOHOST_ADDR", "0x708"), 0),
        "counter_protocol": "retire-inclusive-v2",
        "inputs": {str(p.relative_to(ROOT)): sha256(p) for p in paths},
        "project_configuration": {p.name: sha256(p) for p in configuration},
    }
    with tarfile.open(directory / "inputs.tar.gz", "w:gz") as archive:
        for path in paths:
            archive.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
        # Keep exact project settings as text, without creating project files.
        for path in configuration:
            archive.add(path, arcname=f"configuration/{path.name}.txt", recursive=False)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def finalize(directory):
    """Only complete evidence may become a reusable synthesis replica."""
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    if manifest["fingerprint"] != source_fingerprint():
        raise SystemExit("Sources changed during compilation")
    for name, expected in manifest["inputs"].items():
        if sha256(ROOT / name) != expected:
            raise SystemExit(f"Input changed during compilation: {name}")
    required = ["timing.rpt", "fit.summary", "compile.log", "fmax.txt",
                f"rv32im_{manifest['architecture']}.sof"]
    prepared = datetime.fromisoformat(manifest["prepared_at"]).timestamp()
    for name in required:
        artifact = directory / name
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise SystemExit(f"Missing or empty evidence: {artifact}")
        if artifact.stat().st_mtime < prepared:
            raise SystemExit(f"Stale evidence: {artifact}")
    manifest["artifacts"] = {name: sha256(directory / name) for name in required}
    manifest["artifacts"]["inputs.tar.gz"] = sha256(directory / "inputs.tar.gz")
    manifest["fmax_mhz"] = float((directory / "fmax.txt").read_text())
    manifest["status"] = "complete"
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    (directory / "meta.json").write_text(json.dumps(manifest, indent=2) + "\n")


def verified(directory, fingerprint, elf=None, tohost_addr=None):
    """Check provenance and artifact integrity without adopting old metadata."""
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
        required = {"timing.rpt", "fit.summary", "compile.log", "fmax.txt",
                    "inputs.tar.gz", f"rv32im_{manifest['architecture']}.sof"}
        if not required.issubset(manifest["artifacts"]):
            return False
        if elf is not None:
            name = str(elf.resolve().relative_to(ROOT))
            if manifest["inputs"].get(name) != sha256(elf):
                return False
        if tohost_addr is not None and manifest["tohost_addr"] != tohost_addr:
            return False
        return (manifest["status"] == "complete"
                and manifest["fingerprint"] == fingerprint
                and all(sha256(directory / name) == digest
                        for name, digest in manifest["artifacts"].items()))
    except (OSError, ValueError, KeyError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "finalize", "check"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--arch", choices=["single_cycle", "pipeline"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--elf", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.arch or not args.seed or not args.elf:
            parser.error("prepare requires --arch, --seed and --elf")
        prepare(args.directory, args.arch, args.seed, args.elf)
    elif args.action == "finalize":
        finalize(args.directory)
    elif not verified(args.directory, source_fingerprint(), args.elf,
                      int(os.environ.get("TOHOST_ADDR", "0x708"), 0)):
        raise SystemExit(f"Incomplete, stale or altered replica: {args.directory}")


if __name__ == "__main__":
    main()
