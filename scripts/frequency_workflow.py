"""Coordinate a full campaign with one operator and isolated fitting jobs."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

import frequency_build as build
from frequency_campaign import (BASE, PROGRAMS, REQUIRED_BOOTS, audited_candidates, candidates,
                                configuration, exclusive, initialize, pending, preferred, search)
from frequency_observation import boot_records, observe, physical_state, rejected_artifacts, select

FIRST_SEED = "fc-seed1"
SEEDS = tuple(range(1, 6))
PAUSE = "pause.request"


def full_args(args):
    if args.program or args.arch or args.seed or args.grid:
        raise ValueError("The full workflow uses all five programs, both architectures and seeds 1–5.")
    return SimpleNamespace(**(vars(args) | {"program": PROGRAMS, "seed": SEEDS}))


def read_campaign(directory: Path) -> tuple[dict | None, dict]:
    config_path = directory / "campaign_manifest.json"
    state_path = directory / "campaign_state.json"
    return (build.load_json(config_path) if config_path.exists() else None,
            build.load_json(state_path) if state_path.exists() else {})


def check_scope(config: dict | None, expected: dict) -> None:
    if config:
        existing = config | {"combinations": [
            {k: v for k, v in item.items() if k != "build_inputs"} for item in config["combinations"]
        ]}
        if any(existing.get(key) != value for key, value in expected.items()):
            raise ValueError("Existing campaign scope or fitting settings differ from the full configuration.")


def completion(directory: Path, config: dict | None, state: dict, *, emit=lambda message: None) -> dict:
    verified = {}
    if not config:
        return verified
    def inspect(combo):
        entries = audited_candidates(combo, directory, state)
        entry, confirmed = preferred(entries, rejected_artifacts(entries))
        if not confirmed or not entry:
            return combo["id"], ("unresolved" if not confirmed else "grid_exhausted", 0)
        records = boot_records(entry[2], entry[3])
        return combo["id"], (physical_state(records), len(records))

    total = len(config["combinations"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, (name, result) in enumerate(pool.map(inspect, config["combinations"]), 1):
            verified[name] = result
            if index % 5 == 0 or index == total:
                emit(f"[{index}/{total}] Audited temporal and physical evidence through {name}")
    return verified


def source_for(args) -> Path:
    return BASE / (args.reuse_from or FIRST_SEED)


def matches_current_inputs(combo: dict) -> bool:
    from gen_mem_config import MEM_CONFIG_TEMPLATE

    inputs = combo["build_inputs"]
    row, _, archive = build.reference(combo["architecture"], combo["program"], combo["seed"])
    if row != inputs["historical_reference"] or archive["tohost_addr"] != inputs["tohost_addr"]:
        return False
    archived = {name.replace("\\", "/"): digest for name, digest in archive["inputs"].items()}
    generated = MEM_CONFIG_TEMPLATE.format(
        imem_path="../../build/imem.mem", dmem_path="../../build/dmem.mem")
    generated_digest = hashlib.sha256(generated.encode()).hexdigest()
    for name, digest in build.synthesis_inputs(inputs).items():
        if name.startswith("build/") or name.endswith("/screen.mif"):
            actual = archived.get(name)
        elif name == "rtl/shared/mem_config.vh":
            actual = generated_digest
        else:
            path = build.ROOT / name
            actual = build.file_fingerprint(path) if path.is_file() else None
        if actual != digest:
            return False
    return True


def plan(directory: Path, args) -> None:
    expected = configuration(full_args(args))
    current, state = read_campaign(directory)
    check_scope(current, expected)
    source = source_for(args)
    original, original_state = read_campaign(source)
    if original is None:
        raise ValueError(f"Missing reuse campaign: {source}")
    if original["threads"] != expected["threads"] or (state and any(
            state.get(key) != original_state.get(key) for key in ("threads", "quartus_version"))):
        raise ValueError("Reuse requires the same Quartus build and fitting thread count.")
    old_combinations = {combo["id"]: combo for combo in original["combinations"]}
    have = completion(directory, current, state)
    available = completion(source, original, original_state)
    frozen = {combo["id"]: combo for combo in current["combinations"]} if current else {}
    reusable = set()
    for combo in expected["combinations"]:
        name = combo["id"]
        old = old_combinations.get(name)
        if (not old or old["requests"] != combo["requests"]
                or available[name][0] != "functional_pass"):
            continue
        inputs = old["build_inputs"]
        if name in frozen and build.synthesis_inputs(inputs) != build.synthesis_inputs(frozen[name]["build_inputs"]):
            continue
        if not current and not matches_current_inputs(old):
            continue
        reusable.add(name)
    done = sum(status == "functional_pass" for status, _ in have.values())
    to_import = {name for name in reusable if name not in have or have[name][0] != "functional_pass"}
    total = len(expected["combinations"])
    print(f"{expected['id']}: {done}/{total} selected, {len(to_import)} reusable from {source.name}, "
          f"{total - done - len(to_import)} remaining after reuse.")
    if to_import:
        print("Reuse is conditional on the same Quartus build and verified archived inputs.")
    logical = available_cpus()
    print(f"Resources: {logical} logical CPUs, {available_memory() // (1024 ** 2)} MiB available "
          f"(0 means unknown), {shutil.disk_usage(BASE.parent).free / (1024 ** 3):.1f} GiB free.")
    print(f"Planned maximum: {job_count(args)} concurrent Quartus candidates, {expected['threads']} fitter threads each.")
    pending_points = sum(len(combo["requests"]) for combo in expected["combinations"]
                         if combo["id"] not in to_import and combo["id"] not in have)
    if pending_points:
        print(f"Pending, uninitialized combinations account for up to {pending_points} grid points.")
    needed_boots = 0
    for combo in expected["combinations"]:
        name = combo["id"]
        status, boots = have.get(name, ("pending", 0))
        if status == "functional_pass" or name in to_import:
            continue
        needed_boots += REQUIRED_BOOTS - min(boots, REQUIRED_BOOTS) if status == "one_boot" else REQUIRED_BOOTS
        print(f"  {name}: {status}, {boots} audited boots")
    print(f"Remaining successful boots after reuse: {needed_boots}. No tool invoked.")


def available_cpus() -> int:
    return len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)


def available_memory() -> int:
    try:
        return int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                        if line.startswith("MemAvailable:"))) * 1024
    except (OSError, StopIteration):
        return 0


def job_count(args) -> int:
    if args.jobs:
        return args.jobs
    # Leave one processor for the operator and reserve 3 GiB per Quartus job.
    by_cpu = max(1, (available_cpus() - 1) // args.threads)
    memory = available_memory()
    by_memory = max(1, (memory - 2 * 1024**3) // (3 * 1024**3)) if memory else 1
    return min(3, by_cpu, by_memory)


def request_pause(directory: Path) -> None:
    if not directory.is_dir():
        raise ValueError("Campaign has not started.")
    try:
        with exclusive(directory):
            pass
    except BlockingIOError:
        (directory / PAUSE).touch()
        print("Pause requested. Active tools can finish within the configured grace period.")
        return
    except OSError as error:
        if os.name == "nt" and error.errno == 13:
            (directory / PAUSE).touch()
            print("Pause requested. Active tools can finish within the configured grace period.")
            return
        raise
    print("There is no active campaign run.")


def board_available(args) -> bool:
    if args.no_board or not sys.stdin.isatty():
        return False
    try:
        result = subprocess.run([args.jtagconfig], check=True, capture_output=True,
                                text=True, errors="replace", timeout=15)
        for chain in re.split(r"(?m)^\s*\d+\)\s+", result.stdout):
            name, _, devices = chain.partition("\n")
            if args.cable.casefold() not in name.casefold():
                continue
            ids = re.findall(r"(?m)^\s*([0-9a-fA-F]{8})\s", devices)
            if len(ids) >= args.device_position:
                return ids[args.device_position - 1].upper() == "02D120DD"
        return False
    except (OSError, subprocess.SubprocessError):
        return False


def require_tools(args) -> None:
    missing = [name for name in (args.quartus_sh, args.quartus_sta) if not shutil.which(name)]
    if missing:
        raise ValueError(f"Missing tools on PATH: {', '.join(missing)}")


def coordinate(directory: Path, config: dict, state: dict, args, emit, stopped, board: bool,
               *, operator_capture=nullcontext) -> dict:
    ready = Queue()
    feedback = Queue()
    tried = set()
    profile = {"waiting_for_candidates_seconds": 0.0, "board_session_seconds": 0.0}
    inhibited = set()

    def publish(combo, entries):
        if not board:
            return
        entry, confirmed = preferred(entries, rejected_artifacts(entries))
        if entry and confirmed:
            ready.put((combo["id"], entry, list(entries)))

    def refresh():
        while True:
            try:
                yield feedback.get_nowait()
            except Empty:
                return

    def feed(pool, combinations, reuse_from):
        subset = dict(config, combinations=combinations)
        return pool.submit(search, directory, subset, state,
                           SimpleNamespace(**(vars(args) | {"reuse_from": reuse_from})),
                           stopped=stopped.is_set, publish=publish, emit=emit, tried=tried, refresh=refresh)

    combos = {combo["id"]: combo for combo in config["combinations"]}
    handled = set()
    followup = set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = feed(pool, config["combinations"], args.reuse_from)
        try:
            if board:
                emit("Waiting for a verified candidate to become available for the board")
            while not stopped.is_set():
                waiting = perf_counter()
                if not board:
                    worker.result()
                    break
                try:
                    name, entry, entries = ready.get(timeout=0.5)
                except Empty:
                    if worker.done():
                        worker.result()
                        remaining = []
                        for combo_id in followup:
                            combo = combos[combo_id]
                            latest = candidates(combo, directory, state, verify=True)
                            publish(combo, latest)
                            if next(pending(latest, tried, rejected_artifacts(latest)), None):
                                remaining.append(combo)
                        if not remaining:
                            followup.clear()
                            if not ready.empty():
                                continue
                            break
                        followup.clear()
                        list(refresh())
                        worker = feed(pool, remaining, None)
                    continue
                finally:
                    profile["waiting_for_candidates_seconds"] += perf_counter() - waiting
                if entry[2] in handled or name in inhibited:
                    continue
                handled.add(entry[2])
                records = boot_records(entry[2], entry[3])
                outcome = physical_state(records)
                if outcome == "functional_pass":
                    continue
                if outcome == "functional_fail":
                    feedback.put(name)
                    followup.add(name)
                    continue
                started = perf_counter()
                try:
                    with exclusive(BASE / ".board"):
                        if stopped.is_set():
                            break
                        entries = candidates(combos[name], directory, state, verify=True)
                        latest, confirmed = preferred(entries, rejected_artifacts(entries))
                        if not confirmed or not latest or latest[2] != entry[2]:
                            raise ValueError("The verified selection changed; review before programming")
                        records = boot_records(latest[2], latest[3])
                        outcome = physical_state(records)
                        if outcome == "functional_pass":
                            continue
                        if outcome in {"failure_needs_review", "inconsistent_boots"}:
                            raise ValueError(f"{outcome}: review existing evidence before continuing")
                        with operator_capture():
                            print(f"\n{name} — {len(records)}/{REQUIRED_BOOTS} verified boots", flush=True)
                            outcome = observe(select(entries), args, prompt_first=True, records=records,
                                              stopped=stopped.is_set)
                        emit(f"{name}: board capture {outcome}")
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    inhibited.add(name)
                    emit(f"{name}: board infrastructure or capture unresolved: {error}")
                    print(f"{name}: {error}. Resume after checking this configuration.", flush=True)
                else:
                    if outcome == "functional_fail":
                        feedback.put(name)
                        followup.add(name)
                finally:
                    profile["board_session_seconds"] += perf_counter() - started
        except (KeyboardInterrupt, EOFError):
            stopped.set()
            emit("Stop requested by operator. Active tools can finish within the configured grace period.")
        finally:
            worker.result()
    return profile


class Stop:
    def __init__(self, marker: Path):
        self.marker = marker
        self.event = Event()

    def set(self) -> None:
        self.event.set()

    def is_set(self) -> bool:
        return self.event.is_set() or self.marker.exists()


def run(directory: Path, args) -> None:
    from frequency_artifacts import export

    expected = configuration(full_args(args))
    current, state = read_campaign(directory)
    check_scope(current, expected)
    (directory / PAUSE).unlink(missing_ok=True)
    stopped = Stop(directory / PAUSE)
    args.jobs = job_count(args)
    sessions = directory / "sessions"
    sessions.mkdir(exist_ok=True)
    identifier = uuid4().hex[:12]
    log = sessions / f"{identifier}.log"
    started = perf_counter()
    console = Lock()
    capturing = Event()

    def emit(message):
        with console:
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"{build.timestamp()} {message}\n")
            if not capturing.is_set():
                print(f"[+{int(perf_counter() - started):4d}s] {message}", flush=True)

    @contextmanager
    def operator_capture():
        with console:
            capturing.set()
        try:
            yield
        finally:
            with console:
                capturing.clear()

    emit(f"{args.id}: checking campaign state. Session log: {log}")
    existing = completion(directory, current, state, emit=emit)
    if len(existing) == len(expected["combinations"]) and all(
            status == "functional_pass" for status, _ in existing.values()):
        emit("All configurations are already validated. Regenerating the academic export")
        export(directory, current, state, args.output, args.latex)
        return

    emit("Checking Quartus tools and the reuse source")
    require_tools(args)
    source = source_for(args)
    original, source_state = read_campaign(source)
    if source == directory or not original or not source_state:
        raise ValueError("Select an existing independent reuse source for the first seed.")
    if original["threads"] != expected["threads"] or (state and any(
            state.get(key) != source_state.get(key) for key in ("threads", "quartus_version"))):
        raise ValueError("Reuse requires the same Quartus build and fitting thread count.")
    args.reuse_from = source.name
    if not current:
        emit(f"Freezing the archived inputs for {len(expected['combinations'])} configurations")
        initialize(directory, full_args(args), stopped=stopped.is_set, emit=emit)
        current, state = read_campaign(directory)
        if not current:
            return
    emit("Checking DE1-SoC availability")
    usable_board = board_available(args) and bool(shutil.which(args.quartus_pgm))
    emit(f"Session started: jobs={args.jobs}, fitter_threads={args.threads}, board={usable_board}, "
         f"free_disk_bytes={shutil.disk_usage(directory).free}, logical_cpu={available_cpus()}, "
         f"available_memory_bytes={available_memory()}")
    profile = {}
    try:
        profile = coordinate(directory, current, state, args, emit, stopped, usable_board,
                             operator_capture=operator_capture)
    finally:
        emit("Generating the academic export from the available evidence")
        build.save_json(sessions / f"{identifier}.json", dict(profile,
            jobs=args.jobs, threads=args.threads, board_available=usable_board,
            interrupted=stopped.is_set(), workflow_wall_seconds=perf_counter() - started))
        export(directory, current, state, args.output, args.latex)
