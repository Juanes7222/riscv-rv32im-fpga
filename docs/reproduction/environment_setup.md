# Entorno de medición

<!-- Generado por scripts/thesis_artifacts.py. Los valores provienen de la corrida descrita en el capítulo de resultados. -->

## Hardware

| Elemento | Especificación |
|---|---|
| FPGA | Intel Cyclone V 5CSEMA5F31C6 |
| Tarjeta | DE1-SoC |
| Reloj del procesador | 50 MHz (PIN_AF14) |
| Objetivo de temporización | 100 MHz (`create_clock -period 10.000`) |

## Herramientas

| Herramienta | Versión |
|---|---|
| quartus | Version 25.1std.0 Build 1129 10/21/2025 SC Lite Edition |
| iverilog | Icarus Verilog version 12.0 (stable) () |
| riscv_gcc | riscv-none-elf-gcc (xPack GNU RISC-V Embedded GCC x86_64) 14.2.0 |
| python | Python 3.12.3 |
| cocotb | 2.0.1 |
| git | 6d6793572c49cc78a59a49b7d3322538b1009f5d |

## Estado del repositorio

- Commit: `6d6793572c49cc78a59a49b7d3322538b1009f5d`
- Huella del RTL y de la configuración de síntesis: `2a6a24f02cafecfad8323680a3f4a8784d2a77648d1cafd659fb7d8156a511cc`

## Requisitos

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export PATH="$PWD/.venv/bin:$PATH"   # cocotb-config y el intérprete del venv
```
