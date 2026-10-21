# Protocolo de medición

<!-- Generado por scripts/thesis_artifacts.py. -->

## 1. Tratamientos

| Tratamiento | Microarquitectura |
|---|---|
| T1 | RV32IM monociclo |
| T2 | RV32IM segmentado en cinco etapas (IF, ID, EX, MEM, WB) |

## 2. Instrumentación

Los contadores están incrustados en el propio procesador (`rtl/shared/perf_counter.sv`), son idénticos en ambas microarquitecturas y no realimentan el datapath (ADR 024):

| Contador | Definición |
|---|---|
| `cycle_count` | Ciclos de reloj desde el reinicio hasta que el programa escribe en `tohost`; el valor queda congelado en ese instante. |
| `instr_retired` | Monociclo: un ciclo por instrucción ejecutada. Pipeline: ciclos en los que `valid_wb = 1`, es decir, instrucciones que se retiran sin burbuja. |

El mismo valor congelado en el silicio es el que muestra la consola VGA, y una aserción del testbench comprueba que coincide con el que reporta la simulación (ADR 042). CoreMark es la excepción: señala el final de la corrida con su propia dirección de tohost (0x5000), distinta de la que vigila el RTL (0x708), y por tanto sus contadores congelados no son comparables con los de la simulación.

## 3. Programas de prueba

| Programa | Propósito |
|---|---|
| `raw_stress` | Cadena de dependencias RAW: mide la eficacia del forwarding. |
| `load_use_stress` | Pares load-use: mide la penalización por hazard de datos. |
| `branch_stress` | Ramas tomadas: mide la penalización por hazard de control. |
| `m_ext_stress` | Multiplicaciones y divisiones: mide el impacto de la extensión M. |
| `coremark_iter10` | Benchmark estándar deprocessors embebidos (EEMBC), diez iteraciones. |

## 4. Procedimiento

1. Verificación funcional de ambas arquitecturas (suites cocotb y `riscv-tests`). Un programa que no pase la verificación no se mide.
2. Síntesis de las cinco réplicas de cada tratamiento (ver `synthesis_protocol.md`).
3. Medición del CPI en simulación con los contadores del procesador, verificada contra el modelo de referencia de Python.
4. Cálculo del throughput de cada réplica como $F_{\max,i}/\mathrm{CPI}$ y del speedup como el cociente de los throughputs pareados por índice.
5. Análisis descriptivo: media, desviación estándar muestral y coeficiente de variación.

## 5. Variables de respuesta

| Variable | Fórmula | Origen |
|---|---|---|
| CPI | $\mathrm{ciclos}/\mathrm{instrucciones}$ | contadores del procesador |
| IPC | $1/\mathrm{CPI}$ | derivado |
| Throughput | $F_{\max}/\mathrm{CPI}$ | Timing Analyzer y contadores |
| Fmax | Timing Analyzer, modelo Slow 85 °C | Quartus |
| Recursos | ALMs, registros, bloques RAM, DSP, bits de memoria, pines | Fitter |
| Latencia | Ciclos hasta `tohost` | contadores del procesador |

## 6. Criterio de evaluación de la hipótesis

Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo: no se aplica ninguna prueba de significancia inferencial, en línea con el anteproyecto (§7.1.8). La hipótesis de trabajo $H_1$ se considera sostenida para un programa cuando el extremo inferior de la dispersión del speedup, $\overline{S} - \sigma_{S}$, es mayor que uno; en caso contrario, $H_0$ no se descarta.

## 7. Resultados por programa

| Programa | CPI monociclo | CPI pipeline | Throughput monociclo (MIPS) | Throughput pipeline (MIPS) | Speedup | Resultado |
|---|---|---|---|---|---|---|
| `branch_stress` | 1.0000 | 1.9998 | 52.92 | 27.23 | 0.515 | H0 no descartada |
| `coremark_iter1` | 1.0001 | 1.3984 | 52.91 | 38.94 | 0.736 | H0 no descartada |
| `coremark_iter10` | 1.0000 | 1.4016 | 52.92 | 38.85 | 0.734 | H0 no descartada |
| `load_use_stress` | 1.0000 | 1.9893 | 52.92 | 27.37 | 0.517 | H0 no descartada |
| `m_ext_stress` | 7.5806 | 8.0260 | 6.98 | 6.78 | 0.972 | H0 no descartada |
| `raw_stress` | 1.0000 | 1.2511 | 52.92 | 43.52 | 0.823 | H0 no descartada |

## 8. Réplicas

- Réplicas por arquitectura: 5 (monociclo) y 5 (pipeline).
- La variabilidad experimental es la de la síntesis: el CPI es determinista en simulación, y el throughput de cada réplica usa el Fmax de esa réplica.
