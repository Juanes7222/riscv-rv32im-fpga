#!/usr/bin/env python3
"""Run and resume a frequency search, then validate its candidates on the board."""
import argparse
import os
import re
import subprocess
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import frequency_build as build
from frequency_timing import clock_request

GRIDS = {"single_cycle": (40, 49), "pipeline": (50, 63)}
PROGRAMS = ("coremark", "raw_stress", "load_use_stress", "branch_stress", "m_ext_stress")
DISCARDED = {"timing_violation", "unrealizable"}
REQUIRED_BOOTS = 2
BASE = build.RESULTS / "frequency_campaign"
PROGRESS_INTERVAL = 20


@contextmanager
def exclusive(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def configuration(args) -> dict:
    combinations = []
    for program in args.program or ["coremark"]:
        for seed in args.seed or [1]:
            for arch in args.arch or GRIDS:
                low, high = args.grid if args.grid else GRIDS[arch]
                if low > high or low < GRIDS[arch][0] or high > GRIDS[arch][1]:
                    raise ValueError(f"Invalid grid for {arch}: {low}–{high}")
                combinations.append({
                    "id": f"{program}/{arch}/s{seed}", "program": program,
                    "architecture": arch, "seed": seed,
                    "requests": [clock_request(mhz) for mhz in range(high, low - 1, -1)],
                })
    return {
        "schema": 1, "id": args.id, "threads": args.threads,
        "minimum_equivalent_boots": REQUIRED_BOOTS, "tie_absolute_speedup": 1e-9,
        "descriptive_rule": "mean paired speedup minus sample standard deviation > 1 in at least 3/5 programs, only on 25 pairs",
        "combinations": list({candidate["id"]: candidate for candidate in combinations}.values()),
    }


def initialize(directory: Path, args, *, stopped=lambda: False, emit=print) -> None:
    manifest = directory / "campaign_manifest.json"
    if manifest.exists():
        raise ValueError("Campaign already initialized. Use search to resume.")
    config = configuration(args)
    config["created_at"] = build.timestamp()
    config["git_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=build.ROOT, text=True).strip()
    revisions = set()
    total = len(config["combinations"])
    for index, combination in enumerate(config["combinations"], 1):
        if stopped():
            return
        target = directory / "c" / combination["id"]
        metadata = target / "frozen_inputs.json"
        action = "Verifying frozen inputs for" if metadata.exists() else "Freezing archived inputs for"
        emit(f"[{index}/{total}] {action} {combination['id']}")
        if not metadata.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".freeze-", dir=target.parent) as temporary:
                staged = Path(temporary) / "snapshot"
                inputs = build.freeze_inputs(
                    staged, combination["architecture"], combination["program"], combination["seed"])
                build.save_json(staged / metadata.name, inputs)
                staged.rename(target)
        inputs = build.load_json(metadata)
        if (inputs["git_commit"] != config["git_commit"]
                or not build.verify_files(target / "inputs", inputs["inputs"])):
            raise ValueError(f"Incompatible or damaged frozen inputs: {combination['id']}")
        revisions.add(inputs["rtl_fingerprint"])
        if len(revisions) != 1:
            raise ValueError("RTL or synthesis files changed while preparing the campaign.")
        combination["build_inputs"] = inputs
    build.save_json(manifest, config)


def candidates(combination: dict, directory: Path, state: dict, *, verify=False) -> list:
    result = []
    inputs = combination["build_inputs"]
    for request in combination["requests"]:
        target = directory / "c" / combination["id"] / str(request["requested_mhz"])
        attempts = sorted(target.glob("a*"), key=lambda path: int(path.name[1:]), reverse=True)
        manifest = None
        for attempt in attempts:
            try:
                current = build.load_json(attempt / "manifest.json")
            except (OSError, ValueError):
                continue
            if manifest is None:
                manifest = current
                selected = attempt
            if not verify:
                break
            if current["status"] in build.TERMINAL:
                verified = build.verified_candidate(attempt, inputs, request, state.get("quartus_version"),
                                                    state.get("threads"))
                if verified:
                    manifest = verified
                    break
        else:
            attempt = selected if manifest else None
            if manifest and verify and manifest["status"] in build.TERMINAL:
                manifest = {**manifest, "status": "integrity_error"}
        result.append((request, target, attempt, manifest or {"status": "pending"}))
    return result


def audited_candidates(combination: dict, directory: Path, state: dict) -> list:
    snapshot = directory / "c" / combination["id"] / "inputs"
    if not build.verify_files(snapshot, combination["build_inputs"]["inputs"]):
        raise ValueError(f"Frozen inputs changed: {combination['id']}")
    entries = candidates(combination, directory, state, verify=True)
    for i, (request, target, attempt, manifest) in enumerate(entries):
        if manifest["status"] in {"timing_pass", "timing_violation"}:
            try:
                build.audit_timing(attempt, manifest)
            except (OSError, ValueError, KeyError, TypeError) as error:
                entries[i] = request, target, attempt, dict(manifest, status="integrity_error",
                                                           reason=str(error))
    return entries


def preferred(entries: list, rejected: set | None = None):
    """Return the best passing entry and whether every higher point is resolved."""
    unresolved = False
    for entry in entries:
        _, _, artifact, record = entry
        if record["status"] in DISCARDED or (rejected and artifact in rejected):
            continue
        if record["status"] == "timing_pass":
            return entry, not unresolved
        unresolved = True
    return None, not unresolved


def pending(entries: list, tried: set, rejected: set):
    for entry in entries:
        request, target, artifact, record = entry
        if record["status"] == "timing_pass" and artifact not in rejected:
            break
        if record["status"] not in build.TERMINAL:
            if target not in tried:
                yield entry
            break


def reuse_candidates(directory: Path, config: dict, state: dict, known: dict, original_id: str,
                     *, emit=print, stopped=lambda: False) -> None:
    original = BASE / original_id
    if original == directory:
        raise ValueError("Reuse requires another campaign")
    original_config = build.load_json(original / "campaign_manifest.json")
    original_state = build.load_json(original / "campaign_state.json")
    if any(state[key] != original_state.get(key) for key in ("quartus_version", "threads")):
        raise ValueError("Reuse requires the same Quartus build and fitting thread count")
    originals = {combo["id"]: combo for combo in original_config["combinations"]}
    from frequency_observation import adopt_boots
    for combo in config["combinations"]:
        if stopped():
            return
        old = originals.get(combo["id"])
        if not old:
            continue
        emit(f"{combo['id']}: checking reusable timing and boot evidence from {original_id}")
        if (old["requests"] != combo["requests"]
                or build.synthesis_inputs(old["build_inputs"]) != build.synthesis_inputs(combo["build_inputs"])
                or old["build_inputs"]["historical_reference"] != combo["build_inputs"]["historical_reference"]
                or not build.verify_files(original / "c" / old["id"] / "inputs", old["build_inputs"]["inputs"])):
            raise ValueError(f"Incompatible reuse inputs for {combo['id']}")
        old_entries = {entry[0]["requested_mhz"]: entry for entry in
                       candidates(old, original, original_state, verify=True)}
        for index, entry in enumerate(known[combo["id"]]):
            request, target, _, current = entry
            earlier = old_entries.get(request["requested_mhz"])
            if not earlier or earlier[0] != request or earlier[3]["status"] not in {"timing_pass", "timing_violation"}:
                continue
            old_record = earlier[3]
            if current["status"] in build.TERMINAL:
                if (current["status"] == "timing_pass" and old_record["status"] == "timing_pass"
                        and current.get("origin", {}).get("manifest_sha256")
                        == build.file_fingerprint(earlier[2] / "manifest.json")):
                    adopt_boots(earlier[2], old_record, entry[2], current)
                continue
            number = max((int(path.name[1:]) for path in target.glob("a*")), default=0) + 1
            attempt = target / f"a{number}"
            target.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".reuse-", dir=target) as temporary:
                staged = Path(temporary) / "attempt"
                record = build.adopt(staged, earlier[2], old_record, combo["build_inputs"], config["id"])
                staged.rename(attempt)
            known[combo["id"]][index] = (request, target, attempt, record)
            boots = adopt_boots(earlier[2], old_record, attempt, record) if record["status"] == "timing_pass" else 0
            emit(f"{combo['id']} {request['requested_mhz']} MHz: reused {original_id} "
                 f"({record['status']}, {boots} verified boots)")


def record_interruptions(directory: Path, combination: dict) -> None:
    for path in (directory / "c" / combination["id"]).glob("*/a*/manifest.json"):
        try:
            record = build.load_json(path)
        except (OSError, ValueError):
            continue
        if record.get("status") == "compiling":
            record.update(status="interrupted", finished_at=build.timestamp(),
                          reason="Previous search ended before a verified compile checkpoint")
            build.save_json(path, record)


def search(directory: Path, config: dict, state: dict, args, *, stopped=lambda: False,
           publish=lambda combo, entries: None, emit=print, refresh=lambda: (), tried=None) -> None:
    emit("Checking Quartus Shell and TimeQuest versions")
    version = subprocess.check_output([args.quartus_sh, "--version"], text=True, errors="replace")
    sta_version = subprocess.check_output([args.quartus_sta, "--version"], text=True, errors="replace")
    match = re.search(r"Version .+ Build \d+", version)
    if not match or match[0] not in sta_version:
        raise ValueError("Quartus Shell and TimeQuest must use the same Quartus build")
    identity = {"quartus_version": version.strip(), "threads": config["threads"]}
    if args.reuse_from:
        source_state = build.load_json(BASE / args.reuse_from / "campaign_state.json")
        if any(source_state.get(key) != value for key, value in identity.items()):
            raise ValueError("Reuse requires the same Quartus build and fitting thread count")
    if state and any(state.get(key) != value for key, value in identity.items()):
        raise ValueError("Quartus version or fitting thread count changed. Use a different campaign.")
    state.update(identity)
    state.update(last_search_started=build.timestamp(), jobs=args.jobs)
    build.save_json(directory / "campaign_state.json", state)
    combinations = config["combinations"]
    by_id = {combo["id"]: combo for combo in combinations}
    tried = set() if tried is None else tried
    active = {}
    known = {}
    from frequency_observation import rejected_artifacts
    total = len(combinations)
    emit(f"Checking frozen inputs and previous attempts for {total} configurations")
    for index, combo in enumerate(combinations, 1):
        if stopped():
            return
        snapshot = directory / "c" / combo["id"] / "inputs"
        if not build.verify_files(snapshot, combo["build_inputs"]["inputs"]):
            raise ValueError(f"Frozen inputs changed: {combo['id']}")
        record_interruptions(directory, combo)
        known[combo["id"]] = candidates(combo, directory, state, verify=True)
        if index % 5 == 0 or index == total:
            emit(f"[{index}/{total}] Checked previous attempts through {combo['id']}")
    if args.reuse_from:
        reuse_candidates(directory, config, state, known, args.reuse_from, emit=emit, stopped=stopped)
    for combo in combinations:
        publish(combo, known[combo["id"]])
    excluded = {combo["id"]: rejected_artifacts(known[combo["id"]]) for combo in combinations}
    dispatches = dict.fromkeys(known, 0)
    next_update = monotonic() + PROGRESS_INTERVAL
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        while True:
            running_combinations = {combo["id"] for combo, _, _, _, _ in active.values()}
            for combo_id in refresh():
                if combo_id in known:
                    excluded[combo_id] = rejected_artifacts(known[combo_id])
                    publish(by_id[combo_id], known[combo_id])
            for combo in sorted(combinations, key=lambda c: dispatches[c["id"]]):
                if stopped() or len(active) >= args.jobs:
                    break
                if combo["id"] in running_combinations:
                    continue
                entries = known[combo["id"]]
                next_candidate = next(pending(entries, tried, excluded[combo["id"]]), None)
                if next_candidate is None:
                    continue
                request, target, previous, prior_record = next_candidate
                tried.add(target)
                dispatches[combo["id"]] += 1
                number = max((int(path.name[1:]) for path in target.glob("a*")), default=0) + 1
                attempt = target / f"a{number}"
                resume = ((previous, prior_record) if previous and build.resumable(
                    previous, prior_record, combo["build_inputs"], request, identity["quartus_version"],
                    config["threads"]) else None)
                emit(f"{combo['id']} {request['requested_mhz']} MHz: "
                     f"{'resuming TimeQuest in ' + previous.name if resume else 'starting Quartus in ' + attempt.name}")
                future = executor.submit(build.build, attempt, target.parent,
                                         combo["build_inputs"], request, identity["quartus_version"],
                                         config["threads"], args.quartus_sh, args.quartus_sta,
                                         config["id"], resume)
                active[future] = (combo, request, target, previous if resume else attempt, monotonic())
                running_combinations.add(combo["id"])
            if not active:
                break
            completed, _ = wait(active, timeout=1, return_when=FIRST_COMPLETED)
            for future in completed:
                combo, request, target, attempt, _ = active.pop(future)
                record = future.result()
                entries = known[combo["id"]]
                index = combo["requests"].index(request)
                entries[index] = (request, target, attempt, record)
                timings = ", ".join(f"{stage}={seconds:.1f}s"
                                    for stage, seconds in record.get("stage_seconds", {}).items())
                emit(f"{combo['id']} {request['requested_mhz']} MHz: "
                     f"{record['status']} ({record['reason']})"
                     f"{' [' + timings + ']' if timings else ''}")
                publish(combo, entries)
            now = monotonic()
            if active and now >= next_update:
                details = [f"{combo['id']} {request['requested_mhz']} MHz, "
                           f"{int(now - began)} s, {candidate_activity(attempt, detail=True)}"
                           for combo, request, _, attempt, began in active.values()]
                prefix = "Pause requested; finishing" if stopped() else "Active"
                emit(f"{prefix}: " + " | ".join(details))
                next_update = now + PROGRESS_INTERVAL
    state["last_search_finished"] = build.timestamp()
    build.save_json(directory / "campaign_state.json", state)


def recent_lines(path: Path, limit: int) -> list[str]:
    try:
        with path.open("rb") as stream:
            offset = max(0, stream.seek(0, os.SEEK_END) - 8192)
            stream.seek(offset)
            chunk = stream.read(8192)
    except OSError:
        return []
    lines = chunk.decode("utf-8", errors="replace").splitlines()
    if offset:
        lines = lines[1:]
    if not chunk.endswith((b"\n", b"\r")):
        lines = lines[:-1]
    return [line.strip() for line in lines if line.strip()][-limit:]


def candidate_activity(attempt: Path, *, detail=False) -> str:
    logs = {"setup.log": "Quartus setup", "compile.log": "Quartus compilation",
            "timequest.log": "TimeQuest", "analysis.log": "VGA timing sweep",
            "memory.log": "compiled memory check"}
    paths = [attempt / "setup.log", attempt / "compile.log"]
    for timing in attempt.glob("timing*"):
        paths.extend([timing / "timequest.log", timing / "vga/analysis.log", timing / "memory.log"])
    timestamps = {}
    for path in paths:
        try:
            timestamps[path] = path.stat().st_mtime_ns
        except OSError:
            continue
    if not timestamps:
        return "preparing project"
    latest = max(timestamps, key=timestamps.get)
    lines = recent_lines(latest, 1) if detail else []
    return logs[latest.name] + (f" ({lines[0][:140]})" if lines else "")


def progress(directory: Path, config: dict, state: dict, *, compact=False) -> None:
    print(f"{config['id']}: candidate manifests (use frequency-status to audit evidence)")
    print(f"Configured jobs: {state.get('jobs', 'search not started')}")
    sessions = sorted((directory / "sessions").glob("*.log"), key=lambda path: path.stat().st_mtime)
    if sessions:
        print(f"Latest session log: {sessions[-1]}")
        for line in recent_lines(sessions[-1], 4):
            print(f"  {line}")
    summary = Counter()
    for combo in config["combinations"]:
        entries = candidates(combo, directory, state)
        counts = Counter(record["status"] for _, _, _, record in entries)
        active = [(request, attempt) for request, _, attempt, record in entries
                  if record["status"] in {"compiling", "compiled"}]
        summary["active candidates"] += len(active)
        for request, attempt in active:
            print(f"  {combo['id']} {request['requested_mhz']} MHz: {candidate_activity(attempt, detail=True)}")
        activity = ""
        entry, confirmed = preferred(entries)
        if entry and confirmed:
            count = len(list((entry[2] / "boots").glob("*/observation.json")))
            summary["timing ready"] += 1
            summary["captured boots (unaudited)"] += count
            activity = f"{entry[0]['requested_mhz']} MHz, {count} captured records (unaudited)"
        if not compact:
            print(f"{combo['id']}: " + ", ".join(f"{count} {status}" for status, count in counts.items())
                  + (f" | {activity}" if activity else ""))
    print(" | ".join(f"{count} {label}" for label, count in summary.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "search", "progress", "status", "select", "program",
                                           "observe", "observe-all", "report", "run", "plan", "pause",
                                           "export", "verify"))
    parser.add_argument("--id", default="fc-pilot")
    parser.add_argument("--arch", choices=GRIDS, action="append")
    parser.add_argument("--program", choices=PROGRAMS, action="append")
    parser.add_argument("--seed", type=int, choices=range(1, 6), action="append")
    parser.add_argument("--grid", type=int, nargs=2, metavar=("LOW", "HIGH"))
    parser.add_argument("--jobs", type=int, default=max(1, min(2, (os.cpu_count() or 1) // 4)))
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--reuse-from", metavar="CAMPAIGN_ID")
    suffix = ".exe" if os.name == "nt" or "WSL_DISTRO_NAME" in os.environ else ""
    for tool in ("sh", "sta", "pgm"):
        parser.add_argument(f"--quartus-{tool}", default=f"quartus_{tool}{suffix}")
    parser.add_argument("--cable", default="DE-SoC")
    parser.add_argument("--device-position", type=int, default=2)
    parser.add_argument("--jtagconfig", default=f"jtagconfig{suffix}")
    parser.add_argument("--no-board", action="store_true")
    parser.add_argument("--output", type=Path, help="Academic export directory")
    parser.add_argument("--portable", action="store_true", help="Verify the academic package without local evidence")
    parser.add_argument("--follow", action="store_true", help="Refresh progress while a campaign runs")
    parser.add_argument("--latex", help="Optional pdflatex executable")
    parser.add_argument("--capture", type=Path, help="Copy a VGA screenshot after the readings")
    args = parser.parse_args()
    if (not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", name)
                for name in (args.id, args.reuse_from or args.id))
            or min(args.threads, args.device_position) <= 0 or args.jobs < 0
            or (args.action == "search" and args.jobs == 0)):
        parser.error("Invalid campaign identifier, job count, thread count or JTAG position")
    directory = BASE / args.id
    from frequency_observation import observe, observe_all, program, report, select

    def dispatch():
        from frequency_workflow import PAUSE, plan, request_pause, run
        from frequency_artifacts import export, verify
        if args.action == "plan":
            plan(directory, args)
            return
        if args.action == "pause":
            request_pause(directory)
            return
        if args.action == "run":
            run(directory, args)
            return
        if args.action == "verify":
            verify(directory, args.output, portable=args.portable)
            return
        if args.action == "init":
            initialize(directory, args)
            return
        manifest = directory / "campaign_manifest.json"
        path = directory / "campaign_state.json"
        if args.action == "progress":
            try:
                while True:
                    if manifest.exists():
                        progress(directory, build.load_json(manifest),
                                 build.load_json(path) if path.exists() else {}, compact=args.follow)
                    else:
                        frozen = sum(1 for _ in directory.glob("c/*/*/*/frozen_inputs.json"))
                        print(f"{args.id}: campaign manifest not published yet. Frozen configurations: {frozen}")
                    if not args.follow:
                        return
                    sleep(PROGRESS_INTERVAL)
            except KeyboardInterrupt:
                return
        config = build.load_json(manifest)
        state = build.load_json(path) if path.exists() else {}
        if args.action == "search":
            marker = directory / PAUSE
            marker.unlink(missing_ok=True)
            search(directory, config, state, args, stopped=marker.exists)
        elif args.action == "export":
            export(directory, config, state, args.output, args.latex)
        elif args.action in ("status", "report"):
            report(directory, config, state, save=args.action == "report")
        else:
            combo = [c for c in config["combinations"]
                     if (not args.arch or c["architecture"] in args.arch)
                     and (not args.program or c["program"] in args.program)
                     and (not args.seed or c["seed"] in args.seed)]
            if args.action == "observe-all":
                with exclusive(BASE / ".board"):
                    observe_all(directory, combo, state, args)
                return
            if len(combo) != 1:
                raise ValueError("Select exactly one architecture, workload and seed")
            def selected():
                return select(candidates(combo[0], directory, state, verify=True))

            if args.action in ("program", "observe"):
                with exclusive(BASE / ".board"):
                    print(f"Checking timing evidence and SOF for {combo[0]['id']}...", flush=True)
                    action = program if args.action == "program" else observe
                    action(selected(), args)
            else:
                selected()

    try:
        if args.action in ("init", "search", "run"):
            with exclusive(directory):
                dispatch()
        elif args.action == "report":
            with exclusive(directory / "reports"):
                dispatch()
        else:
            dispatch()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    except (KeyboardInterrupt, EOFError):
        parser.exit(130, "Interrupted. Repeat the same Makefile command to resume.\n")


if __name__ == "__main__":
    main()
