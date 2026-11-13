#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/timing_checks
for bench in tb_reset_release_sync tb_debug_snapshot_cdc tb_screen_writer_snapshot tb_vga_panel tb_vga_table; do
    iverilog -g2012 -Irtl/shared -s "$bench" -o "build/timing_checks/$bench.vvp" \
        rtl/shared/reset_release_sync.sv rtl/shared/debug_snapshot_cdc.sv \
        rtl/shared/vga_mem_shadow.sv rtl/shared/vga_rom_shadow.sv \
        rtl/single_cycle/screen_writer_sc.sv rtl/pipeline/screen_writer_pipeline.sv \
        "verification/vga/$bench.sv" > "build/timing_checks/$bench.compile.log" 2>&1
    vvp "build/timing_checks/$bench.vvp" > "build/timing_checks/$bench.log" 2>&1
    if grep -q 'FAIL' "build/timing_checks/$bench.log"; then
        cat "build/timing_checks/$bench.log"
        exit 1
    fi
    printf '%s: PASS\n' "$bench"
done
