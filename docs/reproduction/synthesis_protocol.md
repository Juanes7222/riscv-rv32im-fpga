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

- Fmax media: 36.91 MHz (desviación estándar 0.26 MHz, CV 0.69 %, n = 5)
- Rango: 36.68 MHz a 37.26 MHz

### Pipeline

- Fmax media: 56.61 MHz (desviación estándar 2.10 MHz, CV 3.71 %, n = 5)
- Rango: 53.00 MHz a 58.06 MHz

## 4. Trazabilidad

| Réplica | Commit | Fecha |
|---|---|---|
| single_cycle / 1 | `` |  |
| single_cycle / 2 | `` |  |
| single_cycle / 3 | `` |  |
| single_cycle / 4 | `` |  |
| single_cycle / 5 | `` |  |
| pipeline / 1 | `` |  |
| pipeline / 2 | `` |  |
| pipeline / 3 | `` |  |
| pipeline / 4 | `` |  |
| pipeline / 5 | `` |  |
