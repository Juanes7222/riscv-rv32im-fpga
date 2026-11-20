#!/usr/bin/env python3
"""Plan or capture five independently compiled seeds per workload and architecture."""
import argparse
import csv
import json
import shutil
from datetime import datetime, timezone

from campaign_state import source_fingerprint, file_fingerprint
from replica_manifest import verified
from vga_timing import check_evidence, tool_path
from measure_physical_repetitions import accepted, rows
import hardware_measure as hardware


def accepted_seeds(results, arch, program, rtl, elf, expected):
    valid = {}
    elf_hash = file_fingerprint(elf)
    for row in rows(results / 'physical_replica_observations' / f'{arch}_{program}.csv'):
        try:
            seed = int(row['replica_seed'])
            directory = (results / row['replica_directory']).resolve()
            if (seed not in range(1, 6) or not directory.is_relative_to(results.resolve())
                    or not row.get('date_utc') or 'HALTED=1' not in row.get('notes', '')):
                continue
            metadata = json.loads((directory / 'manifest.json').read_text())
            capture = json.loads((directory / 'capture_inputs.json').read_text())
            sof = directory / f'rv32im_{arch}.sof'
            if (metadata['seed'] != seed or metadata['architecture'] != arch
                    or file_fingerprint(sof) != row.get('sof_sha256')
                    or float(row.get('clock_mhz', 'nan')) != hardware.CPU_CLOCK_MHZ[arch]
                    or float(row.get('fmax_mhz', 'nan')) != float(metadata['fmax_mhz'])
                    or f'Setting SEED = {seed}\n' not in (directory / 'compile.log').read_text()
                    or not verified(directory, rtl, elf, hardware._get_tohost_addr(elf))):
                continue
            memory = (results / row.get('memory_check', '')).resolve()
            if (not memory.is_relative_to(results.resolve()) or not memory.is_file()
                    or file_fingerprint(memory) != row.get('memory_check_sha256')
                    or 'PASS  IMEM:' not in memory.read_text()
                    or any(str(row.get(key, '')) != str(capture.get(key, ''))
                           for key in ['memory_check', 'memory_check_sha256', 'replica_seed'])
                    or capture['sof'] != row.get('sof_sha256')
                    or capture['rtl'] != rtl or capture['elf'] != elf_hash):
                continue
            check_evidence(directory / 'vga_timing', rtl, sof)
            if accepted(row, arch, program, rtl, elf_hash, file_fingerprint(sof), expected, results):
                valid[seed] = row
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return valid


def campaign_observations(results, rtl):
    """Return one verified capture per architecture, workload and seed."""
    captured = {}
    issues = []
    for arch in hardware.VALID_ARCHS:
        for program in hardware.PROGRAMS:
            elf = (hardware.COREMARK_ELF if program == hardware.COREMARK else
                   hardware.REPO_ROOT / 'build/synthetic' / (program + '.elf'))
            if not elf.is_file():
                issues.append(f'{arch}/{program}: executable missing')
                continue
            reference = rows(results / f'benchmark_{program}_{arch}.csv')
            seeds = accepted_seeds(results, arch, program, rtl, elf,
                                   reference[-1] if reference else None)
            captured.update({(arch, program, seed): row for seed, row in seeds.items()})
            if len(seeds) < 5:
                issues.append(f'{arch}/{program}: {len(seeds)}/5 independently compiled and physically verified seeds')
            counters = {(int(row['cycle_count']), int(row['instr_retired'])) for row in seeds.values()}
            if len(counters) > 1:
                issues.append(f'{arch}/{program}: counters differ across seeds')
    for program in hardware.PROGRAMS:
        group = [row for (_, name, _), row in captured.items() if name == program]
        if len({row['elf_sha256'] for row in group}) > 1:
            issues.append(f'{program}: executables differ across captures')
        if len({int(row['instr_retired']) for row in group}) > 1:
            issues.append(f'{program}: retired instruction counts differ across captures')
    return captured, issues


def promote(path, selected):
    previous = rows(path)
    fields = list(dict.fromkeys([*(previous[0] if previous else {}), *selected]))
    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([*previous, selected])
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--check', action='store_true')
    parser.add_argument('--arch', choices=hardware.VALID_ARCHS)
    parser.add_argument('--program', choices=hardware.PROGRAMS)
    parser.add_argument('--recapture-seed', type=int, choices=range(1, 6))
    args = parser.parse_args()
    if args.recapture_seed and not (args.capture and args.arch and args.program):
        parser.error('--recapture-seed requires --capture, --arch and --program')
    rtl = source_fingerprint()
    plan = []
    for arch in ([args.arch] if args.arch else hardware.VALID_ARCHS):
        for program in ([args.program] if args.program else hardware.PROGRAMS):
            elf = hardware.elf_for(program)
            expected = hardware.expected_values(program, arch)
            complete = accepted_seeds(hardware.RESULTS, arch, program, rtl, elf, expected)
            for seed in range(1, 6):
                plan.append({'architecture': arch, 'program': program, 'seed': seed,
                             'elf_sha256': file_fingerprint(elf),
                             'status': 'complete' if seed in complete else 'pending'})
    plan_path = hardware.RESULTS / 'physical_replica_plan.json'
    plan_path.write_text(json.dumps({'rtl_sha256': rtl, 'observations': plan}, indent=2) + '\n')
    print(json.dumps({'observations_required': len(plan),
                      'complete': sum(row['status'] == 'complete' for row in plan)}, indent=2))
    if not args.capture:
        print('No FPGA access performed. Plan: ' + str(plan_path))
        return 2 if args.check and any(row['status'] != 'complete' for row in plan) else 0
    if not args.recapture_seed and all(item['status'] == 'complete' for item in plan):
        return 0
    if not hardware.board_connected():
        raise SystemExit('Powered DE1-SoC not detected.')
    pilot = {hardware.COREMARK, 'raw_stress'}
    for item in sorted(plan, key=lambda row: (row['seed'] != 1 or row['program'] not in pilot,
                                              row['seed'])):
        if args.recapture_seed:
            if item['seed'] != args.recapture_seed:
                continue
        elif item['status'] == 'complete':
            continue
        arch, program, seed = item['architecture'], item['program'], item['seed']
        elf = hardware.elf_for(program)
        expected = hardware.expected_values(program, arch)
        if program != hardware.COREMARK and (not expected
                or expected.get('rtl_sha256') != rtl
                or expected.get('elf_sha256') != item['elf_sha256']
                or expected.get('reference_valid') != 'True'):
            raise SystemExit(f'Current differential reference missing for {arch}/{program}')
        tohost = hardware._get_tohost_addr(elf)
        outputs = hardware.RESULTS / 'physical_replicas' / program / arch
        directory = outputs / f'replica_{seed}'
        prepared = False
        sof = directory / f'rv32im_{arch}.sof'
        if directory.exists() and verified(directory, rtl, elf, tohost):
            try:
                provenance = json.loads((directory / 'capture_inputs.json').read_text())
                prepared = (provenance['rtl'] == rtl
                            and provenance['elf'] == item['elf_sha256']
                            and provenance['sof'] == file_fingerprint(sof))
            except (OSError, ValueError, KeyError):
                pass
        if prepared:
            provenance['sof_path'] = str(sof)
            check_evidence(directory / 'vga_timing', rtl, sof)
            hardware.run(['quartus_pgm.exe', '-c', 'DE-SoC', '-m', 'JTAG', '-o',
                          'P;' + tool_path(sof, 'quartus_pgm.exe') + '@2'])
        else:
            if directory.exists():
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
                archive = hardware.RESULTS / 'archive' / stamp / 'physical_replicas' / program / arch / directory.name
                root = hardware.RESULTS.resolve()
                if not directory.resolve().is_relative_to(root) or not archive.resolve().is_relative_to(root):
                    raise SystemExit('Replica archive path leaves the results directory.')
                archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(directory), str(archive))
            provenance = hardware.prepare_and_program(elf, arch, tohost, seed, outputs)
        print(f'\n{arch}/{program}, independently compiled seed {seed}/5')
        if input('Press and release KEY[0] once, then wait. Observed HALTED (0 or 1): ').strip() != '1':
            raise SystemExit('Completion not confirmed. No observation recorded.')
        values = hardware.ask_vga_values(tohost, coremark=program == hardware.COREMARK, halted=True)
        values['notes'] = f'replica_seed={seed}; HALTED=1; ' + values['notes']
        path = hardware.RESULTS / 'physical_replica_observations' / f'{arch}_{program}.csv'
        hardware.save_csv(path, arch, program, tohost, values, elf, provenance)
        complete = accepted_seeds(hardware.RESULTS, arch, program, rtl, elf, expected)
        if seed not in complete or complete[seed] != rows(path)[-1]:
            raise SystemExit(f'Observation preserved but rejected. Review {path}')
        if len(complete) == 5:
            promote(hardware.hardware_csv_path(arch, program), complete[seed])
    if not (args.arch or args.program):
        _, issues = campaign_observations(hardware.RESULTS, rtl)
        if issues:
            raise SystemExit('\n'.join(issues))
        plan_path.write_text(json.dumps({'rtl_sha256': rtl, 'observations': [
            {**item, 'status': 'complete'} for item in plan
        ]}, indent=2) + '\n')
    print('Requested independent replica observations completed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
