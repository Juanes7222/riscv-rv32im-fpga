# Protocolo de síntesis

<!-- Generado por scripts/thesis_artifacts.py. -->

## 1. Parámetros de la síntesis

| Parámetro | Valor |
|---|---|
| Dispositivo | Cyclone V 5CSEMA5F31C6 |
| Family | Cyclone V |
| Herramienta | Intel Quartus Prime 25.1std (Lite Edition) |
| Restricción de reloj | `create_clock -period 10.000 -name clk [get_ports clk]` |
| Incertidumbre de reloj | 0.100 ns (subida y bajada) |
| Modelos de temporización | Slow 1100 mV 85 °C y Slow 1100 mV 0 °C |
| Semilla del fitter | `SEED = i`, con $i = 1 \dots 5$ |
| Réplicas por arquitectura | 5 |

Las dos microarquitecturas comparten el mismo archivo de restricciones (`synthesis/*/constraints.sdc`), el mismo dispositivo y el mismo reloj: son variables de control del experimento.

## 2. Procedimiento por réplica

1. Regenerar `rtl/shared/mem_config.vh` y `synthesis/*/screen.mif` con la misma imagen de memoria para todas las réplicas.
2. Compilar el proyecto completo (`quartus_sh -t build.tcl <seed>`), que ejecuta análisis y síntesis, mapa, ajuste y Timing Analyzer.
3. Copiar el reporte de temporización (`.sta.rpt`), el resumen del ajustador (`.fit.summary`) y el bitstream (`.sof`) al directorio de la réplica.
4. Extraer la Fmax del modelo Slow 85 °C con `scripts/extract_fmax.py`.
5. Registrar el commit, la huella del RTL, la semilla y la fecha en `meta.json`.

Las réplicas cuyo `meta.json` no coincide con la huella vigente del RTL se consideran obsoletas y se regeneran: `make thesis` las descarta y las repite.

## 3. Resultados obtenidos

### Monociclo

- Fmax media: 49.10 MHz (desviación estándar 1.35 MHz, CV 2.74 %, n = 5)
- Rango: 46.72 MHz a 49.92 MHz

### Pipeline

- Fmax media: 62.15 MHz (desviación estándar 1.03 MHz, CV 1.66 %, n = 5)
- Rango: 60.96 MHz a 63.34 MHz

## 4. Trazabilidad

| Réplica | Commit | Fecha |
|---|---|---|
| single_cycle / 1 | `af0f217c` | 2026-11-06 11:03:14 |
| single_cycle / 2 | `cd27e8f8` | 2026-11-06 11:48:19 |
| single_cycle / 3 | `cd27e8f8` | 2026-11-06 11:50:39 |
| single_cycle / 4 | `cd27e8f8` | 2026-11-06 11:52:55 |
| single_cycle / 5 | `cd27e8f8` | 2026-11-06 11:55:21 |
| pipeline / 1 | `cd27e8f8` | 2026-11-06 11:57:32 |
| pipeline / 2 | `cd27e8f8` | 2026-11-06 11:59:46 |
| pipeline / 3 | `cd27e8f8` | 2026-11-06 12:02:12 |
| pipeline / 4 | `cd27e8f8` | 2026-11-06 12:04:30 |
| pipeline / 5 | `cd27e8f8` | 2026-11-06 12:06:42 |
