# Protocolo de medición

<!-- Generado por scripts/thesis_artifacts.py. -->

> Instrumentación vigente: retire-inclusive-v2 (ADR 053). Los CSV históricos usan la ventana anterior y no acreditan CRC físicos. Las proyecciones que siguen no sustituyen la nueva campaña.

## 1. Tratamientos

| Tratamiento | Microarquitectura |
|---|---|
| T1 | RV32IM monociclo |
| T2 | RV32IM segmentado en cinco etapas (IF, ID, EX, MEM, WB) |

## 2. Instrumentación

Los contadores están incrustados en el propio procesador (`rtl/shared/perf_counter.sv`), son idénticos en ambas microarquitecturas y no realimentan el datapath (ADR 024):

| Contador | Definición |
|---|---|
| `cycle_count` | Ciclos de reloj desde el reinicio hasta que el programa retira la escritura a `tohost`, incluida; el valor queda congelado. |
| `instr_retired` | Monociclo: un ciclo por instrucción ejecutada. Pipeline: ciclos en los que `valid_wb = 1`, es decir, instrucciones que se retiran sin burbuja. La validez es independiente del opcode NOP. |

El mismo valor congelado en el silicio es el que muestra la consola VGA, y una aserción del testbench comprueba que coincide con el que reporta la simulación (ADR 042). CoreMark señala el final de la corrida con su propia dirección de tohost (0x6000) y su bitstream se construye con `TOHOST_ADDR=0x6000` (ADR 047), de modo que el RTL vigila la misma dirección y sus contadores congelados también son comparables con los de la simulación.

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
3. Medición del CPI en simulación con los contadores del procesador, con comparación de registros, memoria y conteo contra el modelo de Python cuando VALIDATION_REFERENCE=1. El registro histórico original no incluye esta validación para todos los benchmarks.
4. Cálculo del throughput de cada réplica como $F_{\max,i}/\mathrm{CPI}$ y del speedup temporal como media de T_monociclo/T_pipeline pareados por índice; T = ciclos/(frecuencia en MHz × 10^6). El emparejamiento es descriptivo y no garantiza menor varianza.
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

Con $n = 5$ implementaciones por tratamiento, el análisis es descriptivo. La siguiente regla adicional no es un intervalo de confianza ni se atribuye retrospectivamente al anteproyecto. La hipótesis $H_1$ se considera sostenida para un programa cuando el extremo inferior de la dispersión del speedup, $\overline{S} - \sigma_{S}$, es mayor que uno; en caso contrario, $H_0$ no se descarta.

## 7. Resultados por programa

| Programa | CPI monociclo | CPI pipeline | Throughput monociclo (MIPS) | Throughput pipeline (MIPS) | Speedup | Resultado |
|---|---|---|---|---|---|---|
| `branch_stress` | 1.0000 | 1.5004 | 49.10 | 41.42 | 0.845 | H0 no descartada |
| `coremark_iter1` | 1.0001 | 1.2744 | 49.09 | 48.77 | 0.996 | H0 no descartada |
| `coremark_iter10` | 1.0000 | 1.2780 | 49.10 | 48.63 | 0.991 | H0 no descartada |
| `load_use_stress` | 1.0000 | 1.8915 | 49.10 | 32.86 | 0.670 | H0 no descartada |
| `m_ext_stress` | 7.5806 | 7.8377 | 6.48 | 7.93 | 1.233 | H1 sostenida |
| `raw_stress` | 1.0000 | 1.1273 | 49.10 | 55.13 | 1.125 | H1 sostenida |

## 8. Réplicas

- Réplicas por arquitectura: 5 (monociclo) y 5 (pipeline).
- La variabilidad experimental es la de la síntesis: el CPI es determinista en simulación, y el throughput de cada réplica usa el Fmax de esa réplica.
- La campaña histórica conserva una lectura CoreMark por arquitectura; no acredita cinco ejecuciones físicas ni CRC correctos. La proyección de ciclos deterministas sobre cinco frecuencias es una adaptación metodológica y no sustituye comprobar cada bitstream en placa.
