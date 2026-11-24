"""Bind repeated board captures to a fitted SOF and report paired performance."""
import csv
import shlex
import math
import shutil
import statistics
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path
from time import perf_counter

import frequency_build as build
from frequency_campaign import PROGRAMS, REQUIRED_BOOTS, audited_candidates, candidates, preferred
from hardware_measure import _parse_int, ask_vga_values
from coremark_hardware import CRC_METHOD, ITERATIONS, check_observation, save_observation


def adoption_matches(directory: Path, row: dict, manifest: dict) -> bool:
    origin = row.get("adopted_boot_from")
    if not origin:
        return True
    source = manifest["origin"]
    if (origin["campaign"] != source["campaign"] or origin["boot"] != row["boot"]
            or origin["candidate_sha256"] != source["manifest_sha256"]):
        return False
    filename = Path("provenance") / origin["campaign"] / "observation.json"
    if filename.as_posix() not in row["evidence"]:
        return False
    original = build.load_json(directory / filename)
    if original["candidate_sha256"] != origin["candidate_sha256"]:
        return False
    return {key: value for key, value in row.items()
            if key not in {"candidate_sha256", "adopted_boot_from", "evidence"}} == {
                key: value for key, value in original.items()
                if key not in {"candidate_sha256", "adopted_boot_from", "evidence"}
            }


def boot_records(attempt: Path, manifest: dict) -> list[dict]:
    records = []
    reference = manifest["inputs"]["historical_reference"]
    paths = sorted((attempt / "boots").glob("*/observation.json"))
    if not paths:
        return records
    candidate_digest = build.file_fingerprint(attempt / "manifest.json")
    for path in paths:
        try:
            row = build.load_json(path)
            if (row["boot"] != int(path.parent.name)
                    or row["candidate_sha256"] != candidate_digest
                    or row["sof_sha256"] != manifest["artifacts"][manifest["sof"]]
                    or row["clock_mhz"] != manifest["clock"]["effective_mhz"]
                    or row["elf_sha256"] != reference["elf_sha256"]
                    or row["architecture"] != manifest["inputs"]["architecture"]
                    or row["program"] != manifest["inputs"]["program"]
                    or not row["halted"] or not build.verify_files(path.parent, row["evidence"])
                    or "program.log" not in row["evidence"]
                    or not adoption_matches(path.parent, row, manifest)
                    or not programming_succeeded((path.parent / "program.log").read_text(errors="replace"))):
                continue
            if row["program"] == "coremark":
                crc_valid, reason = check_observation(
                    row, path.parent, manifest["inputs"]["rtl_fingerprint"],
                    expected_clock_mhz=manifest["clock"]["effective_mhz"])
                if not crc_valid and not (
                    row["crc_status"] == "0x3"
                    and reason == "physical CoreMark reported CRC failure or incomplete execution"
                ):
                    continue
            if row["result"] != functional_outcome(row, reference):
                continue
            records.append(row)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return records


def adopt_boots(source: Path, original: dict, target: Path, manifest: dict) -> int:
    records = boot_records(source, original)
    if not records:
        return 0
    target_digest = build.file_fingerprint(target / "manifest.json")
    for row in records:
        base = source / "boots" / str(row["boot"])
        destination = target / "boots" / str(row["boot"])
        if destination.exists():
            continue
        staging = destination.with_name(f".adopting-{row['boot']}")
        staging.mkdir(parents=True, exist_ok=True)
        for name in row["evidence"]:
            artifact = staging / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base / name, artifact)
        provenance = Path("provenance") / original["campaign_id"] / "observation.json"
        original_observation = staging / provenance
        original_observation.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base / "observation.json", original_observation)
        if build.load_json(original_observation) != row or not build.verify_files(staging, row["evidence"]):
            raise ValueError(f"Observation changed while adopting {base}")
        evidence = {**row["evidence"], provenance.as_posix(): build.file_fingerprint(original_observation)}
        build.save_json(staging / "observation.json", dict(
            row, candidate_sha256=target_digest, evidence=evidence,
            adopted_boot_from={"campaign": original["campaign_id"], "boot": row["boot"],
                               "candidate_sha256": row["candidate_sha256"]},
        ))
        staging.rename(destination)
    adopted = boot_records(target, manifest)
    if len(adopted) < len(records):
        raise ValueError("Adopted boot evidence did not pass audit")
    return len(adopted)


def functional_outcome(row: dict, reference: dict) -> str:
    if (row["exit_status"] == 1
            and (row["program"] != "coremark" or row["crc_status"] == "0x1")
            and all(int(row[key]) == int(reference[key]) for key in ("cycle_count", "instr_retired"))):
        return "functional_pass"
    return "functional_fail"


def physical_state(records: list[dict]) -> str:
    if not records:
        return "pending_validation"
    signatures = {(row["result"], row["exit_status"], row["crc_status"], row["cycle_count"],
                   row["instr_retired"]) for row in records}
    if len(signatures) != 1:
        return "inconsistent_boots"
    if len(records) < REQUIRED_BOOTS:
        return "one_boot"
    if records[0]["result"] == "functional_fail" and not all(
            row["failure_reviewed"] and row["capture"] for row in records):
        return "failure_needs_review"
    return records[0]["result"]


def rejected_artifacts(entries: list) -> set:
    return {attempt for _, _, attempt, manifest in entries if manifest["status"] == "timing_pass"
            and physical_state(boot_records(attempt, manifest)) == "functional_fail"}


def select(entries: list, rejected: set | None = None):
    entry, confirmed = preferred(entries, rejected_artifacts(entries) if rejected is None else rejected)
    if not entry or not confirmed:
        raise ValueError("No selectable timing pass with all higher candidates resolved")
    _, _, attempt, manifest = entry
    print(f"{manifest['clock']['effective_mhz']:.9f} MHz  {attempt / manifest['sof']}")
    print(f"SHA-256: {manifest['artifacts'][manifest['sof']]}")
    return attempt, manifest


def programming_succeeded(output: str) -> bool:
    return "Info (209007): Configuration succeeded" in output


def next_attempt(parent: Path) -> Path:
    number = max((int(path.name) for path in parent.iterdir() if path.name.isdecimal()),
                 default=0) if parent.exists() else 0
    directory = parent / str(number + 1)
    directory.mkdir(parents=True)
    return directory


def load_sof(attempt: Path, manifest: dict, args, directory: Path) -> Path:
    sof = attempt / manifest["sof"]
    if build.file_fingerprint(sof) != manifest["artifacts"][manifest["sof"]]:
        raise ValueError("SOF changed before programming")
    relative = sof.relative_to(build.ROOT).as_posix()
    command = [args.quartus_pgm, "-c", args.cable, "-m", "JTAG", "-o",
               f"P;{relative}@{args.device_position}"]
    log = directory / "program.log"
    print(f"$ {shlex.join(command)}", flush=True)
    print(f"Programming log: {log}", flush=True)
    configured = False
    with log.open("w", encoding="utf-8") as stream:
        with subprocess.Popen(command, cwd=build.ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace") as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                stream.write(line)
                stream.flush()
                configured |= programming_succeeded(line)
            if process.wait() != 0 or not configured:
                raise ValueError(f"Quartus did not confirm FPGA configuration. See {log}")
    return sof


def program(selected, args) -> None:
    attempt, manifest = selected
    directory = next_attempt(attempt / "programming")
    sof = load_sof(attempt, manifest, args, directory)
    build.save_json(directory / "program.json", {
        "programmed_at": build.timestamp(),
        "sof_sha256": manifest["artifacts"][manifest["sof"]],
        "candidate_sha256": build.file_fingerprint(attempt / "manifest.json"),
        "sof": sof.relative_to(attempt).as_posix(),
        "program_log_sha256": build.file_fingerprint(directory / "program.log"),
        "cable": args.cable, "device_position": args.device_position,
    })


def observe(selected, args, *, prompt_first=False, records=None, stopped=lambda: False) -> str:
    attempt, manifest = selected
    if not sys.stdin.isatty():
        raise ValueError("Manual FPGA capture requires an interactive terminal")
    if records is None:
        records = boot_records(attempt, manifest)
    ensure_consistent_boots(records)
    if len(records) >= REQUIRED_BOOTS:
        outcome = physical_state(records)
        print(f"Boot evidence already recorded ({len(records)}/{REQUIRED_BOOTS}): {outcome}")
        return outcome

    waiting = perf_counter()
    if prompt_first:
        input("Set RUN, hold KEY[0], then press Enter to program this bitstream: ")
    else:
        print("The board must be in RUN with KEY[0] held before this command starts.", flush=True)
    while len(records) < REQUIRED_BOOTS and not stopped():
        print(f"Valid boot slots {len(records)}/{REQUIRED_BOOTS}. Starting slot {len(records) + 1}.")
        operator_wait = perf_counter() - waiting
        records = capture_boot(attempt, manifest, args, operator_wait=operator_wait)
        print(f"Verified boot records: {len(records)}/{REQUIRED_BOOTS}", flush=True)
        ensure_consistent_boots(records)
        waiting = perf_counter()
        if len(records) < REQUIRED_BOOTS and not stopped():
            input("Hold KEY[0] again, then press Enter to program the next boot (Ctrl+C to stop): ")
    outcome = physical_state(records)
    print(outcome)
    return outcome


def observe_all(directory: Path, combinations: list[dict], state: dict, args) -> None:
    if not sys.stdin.isatty():
        raise ValueError("Manual FPGA capture requires an interactive terminal")
    for combo in combinations:
        entries = candidates(combo, directory, state, verify=True)
        boots = {attempt: boot_records(attempt, manifest)
                 for _, _, attempt, manifest in entries if manifest["status"] == "timing_pass"}
        rejected = {attempt for attempt, records in boots.items() if physical_state(records) == "functional_fail"}
        entry, confirmed = preferred(entries, rejected)
        if not entry or not confirmed:
            print(f"{combo['id']}: waiting for temporal search")
            continue
        records = boots[entry[2]]
        if physical_state(records) == "functional_pass":
            print(f"{combo['id']}: already validated")
            continue
        print(f"{combo['id']}: {len(records)}/{REQUIRED_BOOTS} verified boot records", flush=True)
        observe(select(entries, rejected), args, prompt_first=True, records=records)


def ensure_consistent_boots(records: list[dict]) -> None:
    if physical_state(records) == "inconsistent_boots":
        raise ValueError("Investigate inconsistent boots and preserve the original evidence")


def capture_boot(attempt: Path, manifest: dict, args, *, operator_wait=0.0) -> list[dict]:
    directory = next_attempt(attempt / "boots")
    boot = int(directory.name)
    started = perf_counter()
    sof = load_sof(attempt, manifest, args, directory)
    programmed = perf_counter()
    print("Release KEY[0] once and wait for HALTED=1. Leave LOAD and STEP untouched.")
    if input("Was KEY[0] held throughout programming? [y/N]: ").strip().lower() not in {"y", "yes", "s", "si", "sí"}:
        raise ValueError("Retry this command with KEY[0] held from before programming to ensure a fresh boot.")
    if input("Read HALTED (1 to confirm): ").strip() != "1":
        raise ValueError("Execution/capture unresolved. Check programming, reset, and VGA before retrying.")
    inputs = manifest["inputs"]
    coremark = inputs["program"] == "coremark"
    try:
        values = ask_vga_values(inputs["tohost_addr"], coremark, halted=True)
    except SystemExit as error:
        raise ValueError(f"Invalid capture. {error}") from error
    if coremark:
        if values["crc_status"] not in {"0x1", "0x3"}:
            raise ValueError("CoreMark requires a conclusive x5/t0 reading")
        exit_status = int(values["crc_status"], 0)
    else:
        exit_status = _parse_int(input("Observed x10/a0 at HALTED (decimal or 0xhex): "))
    capture = None
    if args.capture:
        capture = directory / f"vga{args.capture.suffix}"
        shutil.copyfile(args.capture, capture)
    row = dict(
        values, boot=boot, date_utc=build.timestamp(), clock_mhz=manifest["clock"]["effective_mhz"],
        candidate_sha256=build.file_fingerprint(attempt / "manifest.json"),
        architecture=inputs["architecture"], program=inputs["program"],
        source="vga_console", halted=True, key0_held_during_programming=True,
        exit_status=exit_status, tohost_addr=hex(inputs["tohost_addr"]),
        counter_protocol="retire-inclusive-v2", rtl_sha256=inputs["rtl_fingerprint"],
        sof_sha256=build.file_fingerprint(sof), elf_sha256=inputs["historical_reference"]["elf_sha256"],
        capture=capture.name if capture else "", failure_reviewed=False,
    )
    if row["sof_sha256"] != manifest["artifacts"][manifest["sof"]]:
        raise ValueError("SOF changed during capture")
    row["result"] = functional_outcome(row, inputs["historical_reference"])
    if row["result"] == "functional_fail":
        row["failure_reviewed"] = input(
            "After checking RUN, reset, memory check and VGA readings, type REVIEWED to confirm the discrepancy: "
        ).strip() == "REVIEWED"
    row["stage_seconds"] = {
        "ready_prompt": operator_wait, "programming": programmed - started,
        "operator_and_execution": perf_counter() - programmed,
    }
    if coremark:
        elf = attempt / "project" / inputs["elf"]
        if build.file_fingerprint(elf) != row["elf_sha256"]:
            raise ValueError("ELF changed during capture")
        local_sof = directory / "hardware_bitstreams" / f"{row['sof_sha256']}.sof"
        local_sof.parent.mkdir()
        shutil.copyfile(sof, local_sof)
        memory = directory / "memory.log"
        shutil.copyfile(attempt / manifest["memory_log"], memory)
        if build.file_fingerprint(memory) != manifest["artifacts"][manifest["memory_log"]]:
            raise ValueError("Compiled memory verification changed during capture")
        row.update(iterations=ITERATIONS, crc_method=CRC_METHOD, memory_check=memory.name,
                   memory_check_sha256=build.file_fingerprint(memory))
        row["crc_evidence"] = save_observation(row, elf, directory)
    row["evidence"] = build.hashes(directory, (p for p in directory.rglob("*") if p.is_file()))
    build.save_json(directory / "observation.json", row)
    records = boot_records(attempt, manifest)
    if row not in records:
        raise ValueError("Boot evidence did not pass audit")
    return records


def metrics(row: dict) -> dict:
    cycles = row["cycle_count"]
    instructions = row["instr_retired"]
    seconds = cycles / (row["clock_mhz"] * 1e6)
    return {"cycles": cycles, "instructions_retired": instructions, "cpi": cycles / instructions,
            "ipc": instructions / cycles, "nominal_seconds": seconds,
            "instructions_per_second": instructions / seconds}


def paired_results(accepted: dict, tie: float) -> tuple[list, dict, bool | None]:
    pairs = []
    summaries = {}
    for program in PROGRAMS:
        group = []
        for seed in range(1, 6):
            mono = accepted.get((program, "single_cycle", seed))
            seg = accepted.get((program, "pipeline", seed))
            if not mono or not seg or mono["elf_sha256"] != seg["elf_sha256"]:
                continue
            m, p = metrics(mono), metrics(seg)
            speedup = m["nominal_seconds"] / p["nominal_seconds"]
            cycle_ratio = p["cycles"] / m["cycles"]
            frequency_ratio = seg["clock_mhz"] / mono["clock_mhz"]
            group.append(dict(program=program, seed=seed, speedup=speedup,
                              cycle_ratio=cycle_ratio, frequency_ratio=frequency_ratio,
                              required_frequency_increase_pct=(cycle_ratio - 1) * 100,
                              achieved_frequency_increase_pct=(frequency_ratio - 1) * 100,
                              time_reduction_pct=(1 - p["nominal_seconds"] / m["nominal_seconds"]) * 100,
                              single_cycle_mhz=mono["clock_mhz"], pipeline_mhz=seg["clock_mhz"],
                              single_cycle=m, pipeline=p))
        pairs.extend(group)
        if group:
            speeds = [x["speedup"] for x in group]
            sd = statistics.stdev(speeds) if len(speeds) >= 2 else None
            mean = statistics.mean(speeds)
            def describe(values):
                return dict(mean=statistics.mean(values), minimum=min(values), maximum=max(values),
                            sample_sd=statistics.stdev(values) if len(values) >= 2 else None)

            summaries[program] = dict(
                pairs=len(speeds), mean=mean, sample_sd=sd, minimum=min(speeds), maximum=max(speeds),
                pipeline=sum(x > 1 + tie for x in speeds),
                single_cycle=sum(x < 1 - tie for x in speeds),
                ties=sum(math.isclose(x, 1, rel_tol=0, abs_tol=tie) for x in speeds),
                frequency_sample_sd_mhz={arch: statistics.stdev(x[f"{arch}_mhz"] for x in group)
                                         if len(group) >= 2 else None
                                         for arch in ("single_cycle", "pipeline")},
                meets_descriptive_rule=mean - sd > 1 if len(group) == 5 else None,
                by_architecture={
                    arch: {
                        "clock_mhz": describe([x[f"{arch}_mhz"] for x in group]),
                        "nominal_seconds": describe([x[arch]["nominal_seconds"] for x in group]),
                    } for arch in ("single_cycle", "pipeline")
                },
            )
    support = sum(x["meets_descriptive_rule"] for x in summaries.values()) >= 3 if len(pairs) == 25 else None
    return pairs, summaries, support


def report(directory: Path, config: dict, state: dict, *, save: bool, verbose=True) -> dict:
    from thesis_artifacts import parse_fit_summary

    started = perf_counter()
    rows = []
    selections = []
    accepted = {}
    observations = []
    profiles = {}
    def verified_entries(combo):
        return audited_candidates(combo, directory, state)

    with ThreadPoolExecutor(max_workers=max(1, min(4, len(config["combinations"])))) as executor:
        evidence = list(executor.map(verified_entries, config["combinations"]))
    for combo, entries in zip(config["combinations"], evidence):
        best_timing, timing_confirmed = preferred(entries)
        boots = {attempt: boot_records(attempt, manifest)
                 for _, _, attempt, manifest in entries if manifest["status"] == "timing_pass"}
        rejected = {attempt for attempt, records in boots.items() if physical_state(records) == "functional_fail"}
        chosen, confirmed = preferred(entries, rejected)
        summary = {"combination": combo["id"], "timing_complete": timing_confirmed,
                   "highest_timing_mhz": None, "highest_physical_mhz": None}
        if best_timing and timing_confirmed:
            summary["highest_timing_mhz"] = best_timing[3]["clock"]["effective_mhz"]
        for request, _, attempt, manifest in entries:
            attempted = manifest["status"]
            if not manifest.get("origin"):
                for stage, seconds in manifest.get("stage_seconds", {}).items():
                    profiles.setdefault(stage, []).append(seconds)
            physical = "not_eligible" if attempted in {"timing_violation", "unrealizable"} else "pending"
            boot_count = invalid_boot_count = 0
            selected_observation = None
            if attempted == "timing_pass":
                records = boots[attempt]
                boot_count = len(records)
                invalid_boot_count = len(list((attempt / "boots").glob("*/observation.json"))) - boot_count
                physical = physical_state(records)
                if chosen and attempt == chosen[2] and confirmed and physical == "functional_pass":
                    row = records[0]
                    accepted[(combo["program"], combo["architecture"], combo["seed"])] = row
                    summary["highest_physical_mhz"] = row["clock_mhz"]
                    physical = "selected"
                    fit = next((attempt / name for name in manifest["artifacts"]
                                if name.endswith(".fit.summary")), None)
                    selected_observation = dict(
                        program=combo["program"], architecture=combo["architecture"], seed=combo["seed"],
                        boot_evidence=row, metrics=metrics(row),
                        resources=parse_fit_summary(fit) if fit else {},
                        historical_reference=manifest["inputs"]["historical_reference"],
                        origin=manifest.get("origin"), inputs=manifest["inputs"],
                        quartus_version=manifest["quartus_version"], threads=manifest["threads"],
                        candidate_manifest_sha256=build.file_fingerprint(attempt / "manifest.json"),
                        boots=[dict(number=item["boot"], evidence=item,
                                    sha256=build.file_fingerprint(attempt / "boots" /
                                                                  str(item["boot"]) / "observation.json"))
                               for item in records],
                    )
            requested = request["requested_mhz"]
            checks = manifest.get("checks", {})
            def slack(analysis):
                return min((x["slack_ns"] for key, x in checks.items()
                            if key.split("/")[1] == analysis and x["slack_ns"] is not None), default=None)
            decision = {"timing_violation": "discarded_timing", "unrealizable": "unrealizable",
                        "timing_pass": "timing_accepted"}.get(attempted, "undetermined")
            if physical == "functional_fail":
                decision = "discarded_functional"
            elif physical == "selected":
                decision = "selected"
            row = dict(combination=combo["id"], seed=combo["seed"], requested_mhz=requested,
                       expected_mhz=request.get("expected_mhz"),
                       effective_mhz=manifest.get("clock", {}).get("effective_mhz"),
                       compilation=manifest.get("compilation", "not_started"), status=attempted,
                       decision=decision, reason=manifest.get("reason", ""), physical=physical, boots=boot_count,
                       invalid_boot_records=invalid_boot_count,
                       **{f"{stage}_s": manifest.get("stage_seconds", {}).get(stage) for stage in
                          ("prepare", "quartus_compile", "checkpoint", "timequest", "vga_sweep", "memory", "seal")},
                       setup_ns=slack("setup"), hold_ns=slack("hold"),
                       pulse_width_ns=slack("pulse_width"), recovery_ns=slack("recovery"),
                       removal_ns=slack("removal"), payload_ns=slack("payload_setup"),
                       dac_setup_ns=slack("dac_setup"), dac_hold_ns=slack("dac_hold"),
                       sync_setup_ns=slack("sync_setup"), sync_hold_ns=slack("sync_hold"),
                       attempt=attempt.relative_to(directory).as_posix() if attempt else "",
                       **manifest.get("fmax", {}).get("slow_85C", {"fmax_mhz": None, "restricted_mhz": None}))
            rows.append(row)
            if selected_observation is not None:
                observations.append(dict(selected_observation, candidate=row))
            if verbose:
                print(f"{combo['id']} {requested:2} MHz -> {attempted:17} {physical}")
        summary["upper_timing_grid_limit"] = bool(
            best_timing and timing_confirmed and best_timing[0] == entries[0][0])
        summary["upper_physical_grid_limit"] = bool(
            chosen and chosen[0] == entries[0][0] and summary["highest_physical_mhz"] is not None)
        selections.append(summary)
        if verbose:
            print(summary)
    pairs, summaries, support = paired_results(accepted, config["tie_absolute_speedup"])
    payload = {
        "campaign_id": config["id"], "generated_at": build.timestamp(), "selections": selections,
        "observations": observations, "paired": pairs, "by_program": summaries,
        "descriptive_support": support,
        "timing_profile": {
            "report_wall_seconds": round(perf_counter() - started, 3),
            "new_candidates_by_stage": {
                stage: {"samples": len(values), "median_seconds": statistics.median(values),
                        "total_job_seconds": round(sum(values), 3)}
                for stage, values in profiles.items()
            },
        },
    }
    if save:
        output = directory / "reports"
        output.mkdir(exist_ok=True)
        temporary = output / "candidates.tmp"
        with temporary.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(output / "candidates.csv")
        build.save_json(output / "report.json", payload)
    return dict(payload, candidates=rows)
