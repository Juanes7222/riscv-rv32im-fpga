# Análisis del camino crítico: qué mide cada diseño

Este documento interpreta el resultado medido de la campaña: el pipeline alcanza
una Fmax un 21.4 % por encima del monociclo (58.74 MHz frente a 48.37 MHz,
n = 5) y el monociclo, a cambio, ejecuta una instrucción por ciclo.

La evidencia sale del Timing Analyzer, no de la interpretación:

```console
$ cd synthesis/pipeline && quartus_sta -t report_paths.tcl
$ cd synthesis/single_cycle && quartus_sta -t report_paths.tcl
```

## 1. Los dos caminos críticos

| | Camino crítico | Retardo de datos | Fmax (n = 5) |
|---|---|---|---|
| Monociclo | `instruction_memory:u_imem\|…~PORT_A_WRITE_ENABLE_REG` → `register_file:u_rf\|regs[28][23]` | 17.4 ns | 48.37 MHz (47.58-48.79) |
| Pipeline | `mem_wb_register:u_mem_wb\|wb_csr_addr[10]` → `ex_mem_register:u_ex_mem\|mem_alu_result[28]` | 16.6 ns | 58.74 MHz (57.13-60.28) |

### Monociclo, tramo a tramo

| Tramo | Retardo |
|---|---|
| Reloj → salida de la IMEM (M10K con lectura registrada, ADR 046) | 4.5 ns |
| Decodificación | 1.3 ns |
| Lectura del banco de registros | 2.0 ns |
| Selección del operando A | 2.2 ns |
| **Multiplicador DSP + adder del resultado** | **7.2 ns** |
| Mux de salida de la ALU | 2.9 ns |
| Mux de writeback y captura | 1.0 ns |

El camino del monociclo es **una instrucción completa**: fetch, decodificación,
lectura del banco, ALU y escritura de vuelta, todo en un ciclo.

### Pipeline, tramo a tramo

| Tramo | Retardo |
|---|---|
| Reloj → MEM/WB | 3.9 ns |
| Lectura del CSR | 1.5 ns |
| Mux de writeback y forwarding hacia EX | 2.2 ns |
| **Multiplicador DSP + adder del resultado** | **7.3 ns** |
| Mux de salida de la ALU y captura en EX/MEM | 2.6 ns |

El valor del CSR se reenvía de la etapa de escritura a la de ejecución porque
el banco de registros no se puede leer y escribir en el mismo ciclo; una
multiplicación que use ese valor arrastra el retardo del DSP hasta el
registro EX/MEM.

## 2. Lo que la campaña anterior no veía (ADR 050)

Con las profundidades de memoria que necesita CoreMark (`IMEM_DEPTH = 4096`,
`DMEM_DEPTH = 1024`, ADR 047) las dos arquitecturas perdían frecuencia: el
monociclo bajaba a 28-29 MHz y el pipeline a 47-49 MHz. La causa no era la
memoria sino la **mux de salida compartida de la ALU**: la dirección de carga
y el objetivo de salto se tomaban de `alu_res`, y el peor arco de esa mux es
el multiplicador (7.2 ns), que para esos dos usos es un *don't-care* funcional
(una carga siempre suma, una rama siempre suma).

El adder dedicado (`alu_sum`, ADR 050) devolvió las cifras a su sitio:

| Diseño | Antes del adder dedicado | Después |
|---|---|---|
| Monociclo | 28.15-29.61 MHz | 47.58-48.79 MHz |
| Pipeline | 46.93-48.65 MHz | 57.13-60.28 MHz |

## 3. Por qué el pipeline gana ahora la frecuencia

* El **monociclo** no puede partir su camino: la instrucción entera cabe en
  un ciclo y el camino crítico es la suma de todos sus tramos.
* El **pipeline** parte esa misma ruta en cinco etapas, y su camino más
  largo ya no es una etapa: es el reenvío **CSR (WB) → EX** más la
  multiplicación, porque la rama se resuelve en EX y el PC necesita ese
  resultado para buscar la siguiente instrucción.

El multiplicador aparece en los dos caminos y es funcional en los dos (en el
pipeline, un `mul` puede usar el valor de un CSR reenviado). Lo que el
pipeline no tiene que pagar es la lectura de la IMEM, la decodificación y la
lectura del banco de registros en el mismo tramo.

## 4. La diferencia estructural en área

El desglose del fitter (`Fitter Resource Utilization by Entity`) con la
configuración de la campaña actual:

| | Monociclo | Pipeline |
|---|---|---|
| ALMs | 3 831 | 5 752 |
| Registros | 4 117 | 5 109 |
| Bloques RAM | 60 | 44 |
| DSP | 10 | 10 |
| PLL | 2 (VGA + CPU, ADR 049) | 1 (VGA) |

El pipeline usa más ALMs (los registros de las cinco etapas y las redes de
reenvío) y menos memoria: la memoria de datos del monociclo necesita cuatro
bloques M10K con lectura de medio ciclo (ADR 048) y la del pipeline cuatro con
salida registrada.

## 5. Lectura para el capítulo de resultados

1. El pipeline gana un 21.4 % de frecuencia (58.74 frente a 48.37 MHz), muy
   por encima de la dispersión entre réplicas (CV 0.97 % y 2.04 %).
2. La penalización por hazards sigue siendo de otro orden: el CPI de
   CoreMark es 1.0000 en el monociclo y 1.4018 en el pipeline, de modo que el
   **throughput del monociclo sigue siendo mayor**: 48.37/1.0000 = 48.37 MIPS
   frente a 58.74/1.4018 = 41.91 MIPS (1.15×). En la placa, con el monociclo
   a 40 MHz (ADR 049) y el pipeline a 50 MHz, la comparación es 40.0 MIPS
   frente a 35.7 MIPS (1.12×).
3. La diferencia de frecuencia es, por tanto, real y localizable: el lazo de
   resolución de ramas en EX del pipeline y la ruta completa de una
   instrucción en el monociclo. Ninguno de los dos es ruido de síntesis.

## 6. Advertencia sobre los datos de junio de 2026

Las réplicas de junio de 2026 (36.91 MHz y 56.61 MHz) no son comparables con
estas: eran de un RTL anterior al rediseño de la consola VGA, en el que las
memorias sombra de la consola no se inferían como M10K y el monociclo tenía
17 503 registros. La campaña actual sustituye esos números por los del diseño
que se va a documentar.
