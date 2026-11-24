"""Build candidates in isolated Quartus projects using frozen workload inputs."""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from campaign_state import _source_files, file_fingerprint, source_fingerprint
from frequency_timing import clock_transfer_coverage, fitted_clock, fmax_rows, physical_timing, vga_evidence
from vga_timing import tool_path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DEVICE = "5CSEMA5F31C6"
TERMINAL = {"timing_pass", "timing_violation", "unrealizable"}
SUPPORT = (
    "synthesis/de1soc_pins.tcl", "synthesis/report_physical_timing.tcl",
    "synthesis/report_vga_sensitivity.tcl", "scripts/check_mem_init.py",
    "scripts/frequency_timing.py", "scripts/frequency_build.py",
    "scripts/frequency_campaign.py", "scripts/frequency_observation.py",
    "scripts/vga_timing.py", "scripts/coremark_hardware.py", "scripts/hardware_measure.py",
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def stage_time(record: dict, stage: str):
    start = perf_counter()
    try:
        yield
    finally:
        record.setdefault("stage_seconds", {})[stage] = round(perf_counter() - start, 3)


def save_json(path: Path, document: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def hashes(base: Path, files) -> dict:
    return {path.relative_to(base).as_posix(): file_fingerprint(path) for path in sorted(files)}


def verify_files(base: Path, files: dict) -> bool:
    try:
        return bool(files) and all(
            not Path(name).is_absolute() and ".." not in Path(name).parts
            and file_fingerprint(base / name) == digest for name, digest in files.items())
    except OSError:
        return False


def reference(arch: str, program: str, seed: int) -> tuple[dict, Path, dict]:
    table = RESULTS / "physical_replica_observations" / f"{arch}_{program}.csv"
    with table.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    original = RESULTS / "physical_replicas" / program / arch / f"replica_{seed}"
    metadata = load_json(original / "manifest.json")
    sof = original / f"rv32im_{arch}.sof"
    archive = original / "inputs.tar.gz"
    if (metadata["seed"] != seed or metadata["architecture"] != arch
            or metadata["status"] != "complete"
            or file_fingerprint(archive) != metadata["artifacts"][archive.name]
            or file_fingerprint(sof) != metadata["artifacts"][sof.name]):
        raise ValueError(f"Historical replica provenance mismatch: {original}")
    for row in reversed(rows):
        if (int(row["replica_seed"]) != seed or row["result"] != "pass"
                or (RESULTS / row["replica_directory"]).resolve() != original.resolve()
                or row["sof_sha256"] != metadata["artifacts"][sof.name]
                or row["rtl_sha256"] != metadata["fingerprint"]
                or row["counter_protocol"] != "retire-inclusive-v2"
                or int(row["tohost_addr"], 0) != metadata["tohost_addr"]
                or float(row["fmax_mhz"]) != metadata["fmax_mhz"]
                or "HALTED=1" not in row["notes"]):
            continue
        if program == "coremark":
            from coremark_hardware import check_observation
            valid, reason = check_observation(row, RESULTS, metadata["fingerprint"])
            if not valid:
                raise ValueError(f"CoreMark historical evidence: {reason}")
        else:
            baseline = RESULTS / f"benchmark_{program}_{arch}.csv"
            with baseline.open(newline="") as stream:
                verified_rows = list(csv.DictReader(stream))
            matching_fields = ("architecture", "cycle_count", "instr_retired", "elf_sha256",
                               "rtl_sha256", "counter_protocol", "tohost_addr")
            if not any(candidate.get("result") == "pass"
                       and candidate.get("reference_valid") == "True"
                       and all(candidate.get(key) == row.get(key) for key in matching_fields)
                       for candidate in verified_rows):
                raise ValueError(f"Missing historical differential reference: {arch}/{program}")
        return row, archive, metadata
    raise ValueError(f"No accepted historical observation for {program}/{arch}/{seed}")


def freeze_inputs(directory: Path, arch: str, program: str, seed: int) -> dict:
    row, archive, metadata = reference(arch, program, seed)
    snapshot = directory / "inputs"
    snapshot.mkdir(parents=True, exist_ok=False)
    project_sources = (ROOT / "rtl/shared", ROOT / "rtl" / arch, ROOT / "synthesis" / arch)
    sources = [path for path in _source_files()
               if any(path.is_relative_to(source) for source in project_sources)]
    for path in [*sources, *(ROOT / name for name in SUPPORT)]:
        target = snapshot / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    mem_config = snapshot / "rtl/shared/mem_config.vh"
    from gen_mem_config import MEM_CONFIG_TEMPLATE
    mem_config.write_text(MEM_CONFIG_TEMPLATE.format(
        imem_path="../../build/imem.mem", dmem_path="../../build/dmem.mem"), encoding="utf-8")
    recorded = {name.replace("\\", "/"): digest for name, digest in metadata["inputs"].items()}
    names = ["build/imem.mem", "build/dmem.mem", f"synthesis/{arch}/screen.mif",
             f"build/{'coremark' if program == 'coremark' else 'synthetic'}/{program}.elf"]
    with tarfile.open(archive) as source:
        for name in names:
            data = source.extractfile(name)
            if data is None:
                raise ValueError(f"Missing immutable program input: {name}")
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data.read())
            if file_fingerprint(target) != recorded[name]:
                raise ValueError(f"Archived image changed: {name}")
    if recorded[names[-1]] != row["elf_sha256"]:
        raise ValueError("Archived ELF does not match the physical observation")
    return {
        "architecture": arch, "program": program, "seed": seed, "elf": names[-1],
        "tohost_addr": metadata["tohost_addr"], "device": DEVICE,
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "memory_depth_words": {"imem": 4096, "dmem": 1024},
        "rtl_fingerprint": source_fingerprint(),
        "historical_replica": row["replica_directory"], "historical_reference": row,
        "inputs": hashes(snapshot, (path for path in snapshot.rglob("*") if path.is_file())),
    }


def invoke(command: list[str], cwd: Path, log: Path) -> None:
    with log.open("wb") as output:
        isolation = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
        subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, check=True, **isolation)


def verified_candidate(directory: Path, inputs: dict, request: dict, version: str,
                       threads: int | None = None) -> dict | None:
    try:
        record = load_json(directory / "manifest.json")
        if (record["inputs"] != inputs or record["request"] != request
                or record["quartus_version"] != version
                or (threads is not None and record["threads"] != threads)):
            return None
        if record["status"] == "unrealizable":
            return record if not request["realizable"] else None
        if record["status"] not in TERMINAL or not verify_files(directory, record["artifacts"]):
            return None
        if record["status"] == "timing_pass":
            project = directory / record["sof"]
            if (record["sof"] not in record["artifacts"] or not project.is_file()
                    or record["memory_log"] not in record["artifacts"]):
                return None
            clock = fitted_clock(directory / record.get("timing_directory", "timing") / "clocks.rpt",
                                 request)
            if clock != record["clock"]:
                return None
            clock_transfer_coverage(directory / record.get("timing_directory", "timing"),
                                    clock["fitted_clock"], inputs["architecture"])
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def synthesis_inputs(record: dict) -> dict:
    arch = record["architecture"]
    prefixes = ("rtl/shared/", f"rtl/{arch}/", f"synthesis/{arch}/", "build/")
    shared = {"synthesis/de1soc_pins.tcl", "synthesis/report_physical_timing.tcl",
              "synthesis/report_vga_sensitivity.tcl", "scripts/check_mem_init.py"}
    return {name: digest for name, digest in record["inputs"].items()
            if name.startswith(prefixes) or name in shared}


def audit_timing(original: Path, source: dict) -> None:
    timing = original / source.get("timing_directory", "timing")
    fitted = fitted_clock(timing / "clocks.rpt", source["request"])
    fmax = fmax_rows((original / source["sof"]).with_suffix(".sta.rpt"), fitted["fitted_clock"])
    coverage = clock_transfer_coverage(timing, fitted["fitted_clock"], source["inputs"]["architecture"])
    checks, violations = physical_timing(timing)
    if not violations:
        _, violations = vga_evidence(timing / "vga", write_summary=False)
    if (fitted != source["clock"] or checks != source["checks"]
            or fmax != source["fmax"] or coverage != source.get("transfer_coverage", coverage)):
        raise ValueError("Archived timing reports disagree with the source manifest")
    if bool(violations) != (source["status"] == "timing_violation"):
        raise ValueError("Archived timing decision failed independent verification")
    if source["status"] == "timing_pass":
        memory = (original / source["memory_log"]).read_text()
        if "PASS  IMEM:" not in memory or "RESULT: PASS" not in memory:
            raise ValueError("Missing compiled memory evidence")


def adopt(directory: Path, original: Path, source: dict, inputs: dict, campaign: str) -> dict:
    old_inputs = source["inputs"]
    if (any(inputs[key] != old_inputs[key] for key in
            ("architecture", "program", "seed", "tohost_addr", "device"))
            or synthesis_inputs(inputs) != synthesis_inputs(old_inputs)
            or source["status"] not in {"timing_violation", "timing_pass"}):
        raise ValueError("The original candidate has different compilation or timing inputs")
    audit_timing(original, source)
    directory.mkdir(parents=True)
    for name in [*source["artifacts"], f"project/{inputs['elf']}"]:
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original / name, target)
    if (not verify_files(directory, source["artifacts"])
            or file_fingerprint(directory / "project" / inputs["elf"]) != inputs["inputs"][inputs["elf"]]):
        raise ValueError("Copied candidate did not match its sources")
    origin_path = Path("provenance") / source["campaign_id"] / "manifest.json"
    (directory / origin_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original / "manifest.json", directory / origin_path)
    digest = file_fingerprint(directory / origin_path)
    record = dict(source, inputs=inputs, campaign_id=campaign, adopted_at=timestamp(),
                  origin={"campaign": source["campaign_id"], "candidate": source["candidate_id"],
                          "manifest_path": origin_path.as_posix(), "manifest_sha256": digest})
    record["artifacts"] = {**source["artifacts"], origin_path.as_posix(): digest}
    save_json(directory / "manifest.json", record)
    return record


def compile_checkpoint(project: Path, directory: Path, arch: str) -> dict:
    output = project / "output_files"
    fitted_database = [path for path in (project / "db").glob("*")
                       if path.is_file() and path.suffix in {".cdb", ".hdb", ".vdb", ".mif"}]
    if not fitted_database:
        raise ValueError("Missing fitted Quartus database")
    return hashes(directory, [
        directory / "compile.log", project / f"rv32im_{arch}.qsf",
        output / f"rv32im_{arch}.sof", output / f"rv32im_{arch}.fit.summary",
        output / f"rv32im_{arch}.sta.rpt", *fitted_database,
    ])


def analyze(directory: Path, snapshot: Path, record: dict, sta: str) -> dict:
    manifest = directory / "manifest.json"
    inputs = record["inputs"]
    request = record["request"]
    workspace = directory / "project"
    project = workspace / "synthesis" / inputs["architecture"]
    sof = directory / record["sof"]
    output = sof.parent
    sta_report = sof.with_suffix(".sta.rpt")
    runs = {"timing"} if (directory / "timing").exists() else set()
    runs.update(path.name for path in directory.glob("timing-*"))
    if runs:
        archive = directory / f"analysis-attempt-{len(runs)}.json"
        if not archive.exists():
            save_json(archive, record)
    timing = directory / ("timing" if not runs else f"timing-{len(runs) + 1}")
    record.update(status="compiled", timing_directory=timing.name)
    stage = "timing_error"
    try:
        timing.mkdir()
        for filename, folder, log in (
            ("report_physical_timing.tcl", timing, "timequest.log"),
            ("report_vga_sensitivity.tcl", timing / "vga", "analysis.log"),
        ):
            folder.mkdir(exist_ok=True)
            with stage_time(record, "timequest" if folder == timing else "vga_sweep"):
                invoke([sta, "-t", tool_path(snapshot / "synthesis" / filename, sta),
                        tool_path(project, sta), tool_path(folder, sta)], project, folder / log)
            if folder == timing:
                record["clock"] = fitted_clock(timing / "clocks.rpt", request)
                record["fmax"] = fmax_rows(sta_report, record["clock"]["fitted_clock"])
                record["checks"], violations = physical_timing(timing)
                record["transfer_coverage"] = clock_transfer_coverage(
                    timing, record["clock"]["fitted_clock"], inputs["architecture"])
                if violations:
                    break
            else:
                record["vga_sensitivity"], violations = vga_evidence(folder)
        if violations:
            record.update(status="timing_violation", reason="; ".join(violations))
        else:
            stage = "memory_error"
            memory = timing / "memory.log"
            with stage_time(record, "memory"):
                invoke([sys.executable, str(snapshot / "scripts/check_mem_init.py"), "--project", str(project),
                        "--imem", str(workspace / "build/imem.mem"),
                        "--dmem", str(workspace / "build/dmem.mem")], project, memory)
            if "PASS  IMEM:" not in memory.read_text() or "RESULT: PASS" not in memory.read_text():
                raise ValueError("Missing matching compiled IMEM evidence")
            record.update(status="timing_pass", memory_log=memory.relative_to(directory).as_posix(),
                          reason="All applicable timing and compiled memory checks passed")
        files = [*directory.glob("*.log"), *timing.rglob("*"), *output.glob("*.rpt"),
                 *output.glob("*.summary"), *project.glob("*.q[ps]f"), *project.glob("db/*.hdl.mif"), sof]
        with stage_time(record, "seal"):
            record["artifacts"] = hashes(directory, (path for path in files if path.is_file()))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        record.update(status=stage, reason=str(error))
    record["finished_at"] = timestamp()
    save_json(manifest, record)
    return record


def resumable(directory: Path, record: dict, inputs: dict, request: dict,
              version: str, threads: int) -> bool:
    return (record.get("compilation") == "complete"
            and record.get("status") in {"compiled", "timing_error", "memory_error"}
            and record.get("inputs") == inputs and record.get("request") == request
            and record.get("quartus_version") == version and record.get("threads") == threads
            and verify_files(directory, record.get("compile_checkpoint", {})))


def build(directory: Path, combination: Path, inputs: dict, request: dict,
          version: str, threads: int, sh: str, sta: str, campaign: str,
          previous: tuple[Path, dict] | None = None) -> dict:
    arch = inputs["architecture"]
    snapshot = combination / "inputs"
    if previous and resumable(*previous, inputs, request, version, threads):
        return analyze(previous[0], snapshot, previous[1], sta)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = directory / "manifest.json"
    record = {
        "schema": 1, "campaign_id": campaign,
        "candidate_id": f"{inputs['program']}/{arch}/s{inputs['seed']}/{request['requested_mhz']}",
        "started_at": timestamp(), "status": "compiling", "compilation": "started",
        "quartus_version": version, "threads": threads, "request": request, "inputs": inputs,
    }
    if not request["realizable"]:
        record.update(status="unrealizable", compilation="not_started",
                      reason="No nominal frequency in the requested 1 MHz bin")
        save_json(manifest, record)
        return record
    save_json(manifest, record)
    workspace = directory / "project"
    project = workspace / "synthesis" / arch
    try:
        with stage_time(record, "prepare"):
            for name in ("rtl", "synthesis", "build"):
                shutil.copytree(snapshot / name, workspace / name)
            invoke([sh, "-t", "setup.tcl"], project, directory / "setup.log")
        with stage_time(record, "quartus_compile"):
            invoke([sh, "-t", "build.tcl", str(inputs["seed"]), str(request["multiply_by"]),
                    str(request["divide_by"]), str(inputs["tohost_addr"]), str(threads)],
                   project, directory / "compile.log")
        name = f"rv32im_{arch}"
        output = project / "output_files"
        sof = output / f"{name}.sof"
        summary = output / f"{name}.fit.summary"
        if not sof.stat().st_size or "Fitter Status : Successful" not in summary.read_text():
            raise ValueError("Quartus did not produce a successfully fitted SOF")
        with stage_time(record, "checkpoint"):
            checkpoint = compile_checkpoint(project, directory, arch)
        record.update(status="compiled", compilation="complete", sof=sof.relative_to(directory).as_posix(),
                      compile_checkpoint=checkpoint)
        save_json(manifest, record)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        record.update(status="build_error", reason=str(error), finished_at=timestamp())
        save_json(manifest, record)
        return record
    return analyze(directory, snapshot, record, sta)
