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
| git | f2190227d907017f7718900126dee3c69a0476c4 |

## Estado del repositorio

- Commit: `f2190227d907017f7718900126dee3c69a0476c4`
- Huella del RTL y de la configuración de síntesis: `762738a0d12f7f6230e65d870ef86308b5f8c814f73ac4434bc88e9e26ea323d`

## Requisitos

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export PATH="$PWD/.venv/bin:$PATH"   # cocotb-config y el intérprete del venv
```

## Flujo de reproducción

```bash
make thesis        # campaña completa: sintetiza las réplicas y regenera los artefactos
make thesis-quick  # reutiliza las réplicas de results/ y refresca el resto
```

Ambas campañas terminan con `make check-artifacts`, que compara las tablas de `thesis/tables/` y las figuras de `thesis/figures/diagrams/` con los CSV de `results/` correspondientes (verificación, Fmax, recursos, estadísticas, eficiencia, benchmarks, speedup y CoreMark). Si un artefacto no coincide con su CSV, el objetivo devuelve un código distinto de cero y la campaña falla; el mensaje indica la fila y la columna divergentes. El chequeo también puede ejecutarse por separado después de editar o regenerar artefactos:

```bash
make check-artifacts
```
