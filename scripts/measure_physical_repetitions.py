#!/usr/bin/env python3
"""Plan or capture repeated runs of each workload on one unchanged bitstream.

Planning is read-only with respect to the board. Capture requires a person
to reset the board and read its VGA console for every observation.
"""
import argparse
import csv
import json

from campaign_state import file_fingerprint, source_fingerprint
from vga_timing import check_evidence
import hardware_measure as hardware


def rows(path):
    if not path.is_file():
        return []
    with path.open() as stream:
        return list(csv.DictReader(stream))


def accepted(row, arch, program, rtl, elf_hash, sof_hash, expected, results=None):
    if any(str(row.get(key, '')) != str(value) for key, value in {
        'architecture': arch, 'program': program, 'rtl_sha256': rtl,
        'elf_sha256': elf_hash, 'sof_sha256': sof_hash,
        'counter_protocol': 'retire-inclusive-v2', 'result': 'pass',
    }.items()):
        return False
    try:
        if int(row['cycle_count']) <= 0 or int(row['instr_retired']) <= 0:
            return False
        if expected and any(int(row[key]) != int(expected[key])
                            for key in ('cycle_count', 'instr_retired')):
            return False
    except (KeyError, ValueError):
        return False
    if program == hardware.COREMARK:
        valid, _ = hardware.check_observation(row, results or hardware.RESULTS, rtl)
        return valid
    return (expected is not None and expected.get('rtl_sha256') == rtl
            and expected.get('elf_sha256') == elf_hash
            and expected.get('result') == 'pass'
            and str(expected.get('reference_valid', '')).lower() in ('true', '1'))


def series_counts(results, arch, program, rtl, elf_hash, expected):
    series = {}
    for row in rows(results / 'physical_repetitions' / f'{arch}_{program}.csv'):
        sof_hash = row.get('sof_sha256', '')
        if len(sof_hash) != 64 or any(c not in '0123456789abcdef' for c in sof_hash):
            continue
        artifact = results / 'hardware_bitstreams' / (sof_hash + '.sof')
        if (not artifact.is_file() or file_fingerprint(artifact) != sof_hash
                or 'HALTED=1' not in row.get('notes', '')):
            continue
        try:
            timing = (results / row.get('timing_evidence', '')).resolve()
            if not timing.is_relative_to(results.resolve()):
                continue
            check_evidence(timing, rtl, artifact)
        except (OSError, ValueError, KeyError):
            continue
        if accepted(row, arch, program, rtl, elf_hash, sof_hash, expected, results):
            series.setdefault(sof_hash, set()).add(row.get('date_utc', ''))
    return {sof: len(dates - {''}) for sof, dates in series.items()}


def repetition_issues(results, rtl, required=5):
    """Require real captures of every workload, grouped by unchanged SOF."""
    issues = []
    for arch in hardware.VALID_ARCHS:
        for program in hardware.PROGRAMS:
            elf = (hardware.COREMARK_ELF if program == hardware.COREMARK else
                   hardware.REPO_ROOT / 'build/synthetic' / (program + '.elf'))
            if not elf.is_file():
                issues.append(f'{arch}/{program}: repetition executable missing')
                continue
            reference = rows(results / f'benchmark_{program}_{arch}.csv')
            counts = series_counts(results, arch, program, rtl, file_fingerprint(elf),
                                   reference[-1] if reference else None)
            count = max(counts.values(), default=0)
            if count < required:
                issues.append(f'{arch}/{program}: {count}/{required} verified physical repetitions')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true',
                        help='Program the board and request real VGA observations')
    parser.add_argument('--check', action='store_true',
                        help='Check the required physical repetitions without board access')
    parser.add_argument('--arch', choices=hardware.VALID_ARCHS)
    parser.add_argument('--program', choices=hardware.PROGRAMS)
    parser.add_argument('--repetitions', type=int, default=5)
    args = parser.parse_args()
    if args.capture and args.check:
        parser.error('--capture and --check are mutually exclusive')
    if args.repetitions < 1:
        parser.error('--repetitions must be positive')
    arches = [args.arch] if args.arch else hardware.VALID_ARCHS
    programs = [args.program] if args.program else hardware.PROGRAMS
    rtl = source_fingerprint()
    directory = hardware.RESULTS / 'physical_repetitions'
    directory.mkdir(exist_ok=True)
    plan = {'rtl_sha256': rtl, 'repetitions_per_combination': args.repetitions,
            'purpose': 'Repeated configuration/execution of the same ELF and SOF; not synthesis seeds',
            'combinations': []}
    for arch in arches:
        for program in programs:
            elf = hardware.elf_for(program)
            elf_hash = file_fingerprint(elf)
            expected = hardware.expected_values(program, arch)
            filename = f'{arch}_{program}.csv'
            series = series_counts(hardware.RESULTS, arch, program, rtl, elf_hash, expected)
            completed = max(series.values(), default=0)
            plan['combinations'].append({
                'architecture': arch, 'program': program,
                'elf_sha256': elf_hash,
                'observations_csv': filename,
                'required_observations': args.repetitions,
                'accepted_observations_same_sof': completed,
                'status': 'complete' if completed >= args.repetitions else 'pending',
                'clock_mhz': 40 if arch == 'single_cycle' else 50,
            })
    (directory / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(plan, indent=2))
    if not args.capture:
        print('Plan saved. No observations created and no board access performed.')
        return (2 if args.check and any(item['status'] != 'complete'
                for item in plan['combinations']) else 0)
    if not hardware.board_connected():
        raise SystemExit('Powered DE1-SoC not detected. No capture performed.')
    for item in plan['combinations']:
        arch, program = item['architecture'], item['program']
        elf = hardware.elf_for(program)
        if program == hardware.COREMARK:
            hardware.prepare_hardware_coremark(elf)
        expected = hardware.expected_values(program, arch)
        if program != hardware.COREMARK and (expected is None
                or expected.get('rtl_sha256') != rtl
                or expected.get('elf_sha256') != file_fingerprint(elf)
                or expected.get('result') != 'pass'
                or str(expected.get('reference_valid', '')).lower() not in ('true', '1')):
            raise SystemExit(f'Missing current simulation reference for {arch}/{program}')
        tohost = hardware._get_tohost_addr(elf)
        # Preparation checks the loaded memories and archives their identity.
        provenance = hardware.prepare_and_program(elf, arch, tohost)
        sof = hardware.REPO_ROOT / 'synthesis' / arch / f'output_files/rv32im_{arch}.sof'
        elf_hash, sof_hash = file_fingerprint(elf), file_fingerprint(sof)
        current_rtl = source_fingerprint()
        if current_rtl != rtl or elf_hash != item['elf_sha256']:
            raise SystemExit('Inputs changed during preparation. Generate a new plan.')
        output = directory / item['observations_csv']
        count = series_counts(hardware.RESULTS, arch, program, rtl, elf_hash, expected).get(sof_hash, 0)
        first_capture = True
        while count < args.repetitions:
            if not first_capture:
                # CPU reset does not restore initialized M10K contents.
                # Reload the same SOF for equal starting memory on each run.
                if (file_fingerprint(sof) != sof_hash or file_fingerprint(elf) != elf_hash
                        or source_fingerprint() != rtl):
                    raise SystemExit('Inputs changed between physical repetitions.')
                hardware.run(['make', 'program-direct', f'ARCH={arch}'],
                             extra_env=hardware.make_env(tohost))
            first_capture = False
            print(f'\n{arch}/{program}, observation {count + 1}/{args.repetitions}')
            halted = input('Reset with KEY[0], wait for completion. Observed HALTED (0 or 1): ').strip()
            if halted != '1':
                print('Observation not accepted. Confirm completion before reading counters.')
                continue
            values = hardware.ask_vga_values(tohost, coremark=program == hardware.COREMARK)
            values['notes'] = (f'physical_repetition={count + 1}; HALTED=1; '
                               + values['notes'])
            hardware.save_csv(output, arch, program, tohost, values, elf, provenance)
            observed = rows(output)[-1]
            if not accepted(observed, arch, program, rtl, elf_hash, sof_hash, expected):
                raise SystemExit(f'Observation preserved but rejected. Review {output}')
            count += 1
        # The existing reporting flow reads the canonical CSV. Only promote
        # a combination after all the requested real repetitions passed.
        canonical = hardware.hardware_csv_path(arch, program)
        previous = rows(canonical)
        current = [row for row in rows(output)
                   if accepted(row, arch, program, rtl, elf_hash, sof_hash, expected)][-1]
        fields = list(dict.fromkeys([*(previous[0] if previous else {}), *current]))
        temporary = canonical.with_suffix('.csv.tmp')
        with temporary.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows([*previous, current])
        temporary.replace(canonical)
    print('All requested repetitions completed. Review the archived observations.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
