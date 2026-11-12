"""Bind a physical CRC-gated completion observation to its program and bitstream."""

import csv
import json
import shutil
from pathlib import Path

from campaign_state import file_fingerprint
from measure_benchmarks import prepare_coremark_elf, validate_coremark_elf

ITERATIONS = 2000
CRC_METHOD = "crc-gated-t0-v1"
OBSERVATION_FIELDS = (
    "architecture", "program", "result", "cycle_count", "instr_retired", "iterations",
    "clock_mhz", "rtl_sha256", "elf_sha256", "sof_sha256", "counter_protocol",
    "tohost_addr", "crc_status", "crc_method", "date_utc", "source",
    "memory_check", "memory_check_sha256",
)


def prepare_hardware_coremark(elf: Path) -> None:
    """Preserve an obsolete ELF before rebuilding the full board workload."""
    if elf.exists():
        try:
            validate_coremark_elf(elf, ITERATIONS)
        except ValueError:
            previous = elf.parent / "previous" / f"{file_fingerprint(elf)}.elf"
            previous.parent.mkdir(exist_ok=True)
            if not previous.exists():
                shutil.copy2(elf, previous)
    prepare_coremark_elf(elf, ITERATIONS)


def latest_measurements(results: Path) -> dict:
    """Read the latest physical workload row for each architecture."""
    rows = {}
    for arch in ("single_cycle", "pipeline"):
        path = results / f"hardware_{arch}_coremark_v2.csv"
        if path.is_file():
            with path.open() as stream:
                for row in csv.DictReader(stream):
                    rows[arch] = row
    return rows


def observation_inputs(row: dict, results: Path) -> list:
    """Return the archived files needed to audit one physical observation."""
    files = [results / "hardware_programs" / f"{row.get('elf_sha256', '')}.elf",
             results / "hardware_bitstreams" / f"{row.get('sof_sha256', '')}.sof"]
    for field in ("crc_evidence", "memory_check"):
        if row.get(field):
            files.append(results / row[field])
    return files


def save_observation(row: dict, elf: Path, results: Path) -> str:
    """Archive the ELF and the manually observed physical completion status."""
    validate_coremark_elf(elf, ITERATIONS)
    archived = results / "hardware_programs" / f"{row['elf_sha256']}.elf"
    archived.parent.mkdir(exist_ok=True)
    if not archived.exists():
        shutil.copy2(elf, archived)
    if row.get("crc_status", "") == "":
        return ""
    observation = {key: row[key] for key in OBSERVATION_FIELDS}
    directory = results / "hardware_evidence"
    directory.mkdir(exist_ok=True)
    temporary = directory / "observation.tmp"
    temporary.write_text(json.dumps(observation, indent=2) + "\n")
    path = directory / f"{file_fingerprint(temporary)}.json"
    temporary.replace(path)
    return str(path.relative_to(results))


def check_observation(row: dict, results: Path, fingerprint: str) -> tuple:
    """Verify physical CRC status, counters and archived provenance together."""
    try:
        if row.get("crc_method") != CRC_METHOD or row.get("crc_status", "") == "":
            return False, "physical CRC-gated x5/t0 observation missing"
        if row.get("source") != "vga_console" or row.get("program") != "coremark":
            return False, "observation is not a physical CoreMark console reading"
        if row.get("architecture") not in ("single_cycle", "pipeline"):
            return False, "invalid architecture"
        if row.get("rtl_sha256") != fingerprint or row.get("counter_protocol") != "retire-inclusive-v2":
            return False, "physical source provenance missing or stale"
        if int(row["iterations"]) != ITERATIONS or min(int(row["cycle_count"]), int(row["instr_retired"])) <= 0:
            return False, "invalid physical workload parameters or counters"
        clock = 40 if row["architecture"] == "single_cycle" else 50
        if float(row["clock_mhz"]) != clock or int(row["tohost_addr"], 0) != 0x6000:
            return False, "unexpected physical clock or tohost address"
        archived_elf, archived_sof, *_ = observation_inputs(row, results)
        for path, field in ((archived_elf, "elf_sha256"), (archived_sof, "sof_sha256")):
            if file_fingerprint(path) != row[field]:
                return False, f"archived {field} mismatch"
        validate_coremark_elf(archived_elf, ITERATIONS)
        evidence_path = results / row["crc_evidence"]
        if evidence_path.stem != file_fingerprint(evidence_path):
            return False, "physical observation hash mismatch"
        observation = json.loads(evidence_path.read_text())
        if any(str(observation[key]) != str(row[key]) for key in OBSERVATION_FIELDS):
            return False, "physical observation does not match the measurement row"
        memory_check = results / row["memory_check"]
        memory_log = memory_check.read_text()
        if (file_fingerprint(memory_check) != row["memory_check_sha256"]
                or "RESULT: PASS" not in memory_log or "PASS  IMEM:" not in memory_log):
            return False, "compiled memory image check missing or altered"
        if int(row["crc_status"], 0) != 1:
            return False, "physical CoreMark reported CRC failure or incomplete execution"
        return True, "physical CRC-gated x5/t0 success; raw CRC words were not captured"
    except (OSError, ValueError, KeyError, TypeError) as error:
        return False, f"physical CRC evidence incomplete: {error}"


if __name__ == "__main__":
    prepare_hardware_coremark(Path(__file__).resolve().parents[1] / "build/coremark/coremark.elf")
