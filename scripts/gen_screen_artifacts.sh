#!/usr/bin/env bash
# Regenerates every checked-in artifact derived from scripts/RiscVScreenV3.xlsx:
# the video-memory images, the field maps and the two screen writers.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python

# The repository stores text files with CRLF line endings.
crlf() {
    "$PY" -c "import sys,pathlib; p=pathlib.Path(sys.argv[1]); p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))" "$1"
}

"$PY" scripts/gen_screen_mif.py \
    --xlsx scripts/RiscVScreenV3.xlsx --sheet Single-cycle \
    --out-mif synthesis/single_cycle/screen.mif \
    --out-fields synthesis/single_cycle/fields.json

"$PY" scripts/gen_screen_writer.py \
    --fields-json synthesis/single_cycle/fields.json \
    --out-rtl rtl/single_cycle/screen_writer_sc.sv --mode single_cycle

"$PY" scripts/gen_screen_mif.py \
    --xlsx scripts/RiscVScreenV3.xlsx --sheet Pipeline \
    --out-mif synthesis/pipeline/screen.mif \
    --out-fields synthesis/pipeline/.fields.json

cp synthesis/pipeline/screen.mif rtl/pipeline/screen.mif

"$PY" scripts/gen_screen_writer.py \
    --fields-json synthesis/pipeline/.fields.json \
    --out-rtl rtl/pipeline/screen_writer_pipeline.sv --mode pipeline

for f in synthesis/single_cycle/screen.mif synthesis/single_cycle/fields.json \
         synthesis/pipeline/screen.mif synthesis/pipeline/.fields.json \
         rtl/pipeline/screen.mif \
         rtl/single_cycle/screen_writer_sc.sv rtl/pipeline/screen_writer_pipeline.sv; do
    crlf "$f"
done

echo "screen artifacts regenerated"
