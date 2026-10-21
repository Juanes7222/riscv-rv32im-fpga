# Análisis del camino crítico: por qué el pipeline no gana frecuencia

Este documento interpreta el resultado medido de la campaña: el pipeline alcanza
una Fmax sólo un 2.9 % por encima del monociclo (54.45 MHz frente a 52.92 MHz,
n = 5) y, por tanto, pierde en throughput en todos los programas.

La evidencia sale del Timing Analyzer, no de la interpretación:

```console
$ cd synthesis/pipeline && quartus_sta -t report_paths.tcl
$ cd synthesis/single_cycle && quartus_sta -t report_paths.tcl
```

## 1. Los dos caminos críticos

| | Camino crítico | Retardo de datos |
|---|---|---|
| Monociclo | `pc:u_pc\|pc[5]` → `data_memory:u_dmem\|mem[191]` | 18.4 ns |
| Pipeline | `mem_wb_register:u_mem_wb\|wb_csr_addr[4]` → `if_id_register:u_if_id\|id_instruction[18]` | 18.1 ns |

### Monociclo, etapa por etapa

| Tramo | Retardo |
|---|---|
| Reloj → PC (clock-to-out) | 3.9 ns |
| Lectura de la IMEM (mux) | 2.2 ns |
| Lectura del banco de registros | 0.8 ns |
| **ALU** | **9.1 ns** |
| Escritura en la DMEM (lógica, no M10K) | 4.1 ns |

### Pipeline, etapa por etapa

| Tramo | Retardo |
|---|---|
| **ALU** (resultado de la rama) | ~9 ns |
| Unidad de PC (selección PC+4 / destino de rama) | ~5 ns |
| Lectura de la IMEM | ~2 ns |
| Captura en IF/ID | ~1 ns |

## 2. Por qué las dos implementaciones terminan a la misma frecuencia

Las dos rutas contienen **la misma ALU compartida** (`rtl/shared/alu_rv32im.sv`),
que ocupa la mitad del camino crítico del monociclo, y la misma lectura de la
memoria de instrucciones.

* El **monociclo** ahorra el lazo de retroalimentación de la rama (el PC no
  depende del ALU) pero paga la ruta completa: IMEM → decodificación → ALU →
  escritura en la DMEM.
* El **pipeline** reparte esa ruta en cinco etapas, pero su camino más largo ya
  no es una etapa: es el lazo **ALU (EX) → PC → IMEM → IF/ID**, que existe
  porque la rama se resuelve en EX y el PC necesita ese resultado para buscar la
  siguiente instrucción.

Las dos piezas que el pipeline debería ganar (la decodificación y la escritura
en la DMEM) son, justamente, las que el monociclo pierde frente a ese lazo. El
resultado es una diferencia de 2.9 %, apenas por encima de la dispersión
experimental (CV 1.4 %).

## 3. La diferencia estructural que sí es grande: la memoria de datos

El desglose por entidad del fitter (`Fitter Resource Utilization by Entity`)
muestra dónde está el área:

| Entidad | Monociclo | Pipeline |
|---|---|---|
| `data_memory` / `data_memory_pipe` | **8 969 ALMs** | **39 ALMs** |
| Total del diseño | 11 400 ALMs | 3 634 ALMs |
| Bloques RAM | 31 | 35 |

La causa está en el diseño de las dos memorias:

* `rtl/single_cycle/data_memory.sv`: **lectura asíncrona**. El resultado de un
  load tiene que estar disponible en el mismo ciclo, así que la memoria no puede
  ir en un M10K: el Quartus la implementa en lógica (8 969 ALMs y unas 15 000
  registros para un banco de 512 palabras).
* `rtl/pipeline/data_memory_pipe.sv`: **salida registrada**. El pipeline puede
  registrar la salida de la memoria, el M10K infiere correctamente y la memoria
  ocupa 4 bloques de RAM (los 4 bloques de RAM extra del pipeline) y 39 ALMs.

Es decir: el monociclo paga un precio doble por su organización de un ciclo por
instrucción. No gana ni en frecuencia (el lazo de la rama se lo come) ni en área
(la memoria asíncrona no cabe en un M10K).

## 4. Lectura para el capítulo de resultados

1. La hipótesis H1 no se sostiene con este diseño y esta microarquitectura, y el
   resultado tiene una explicación estructural, no es ruido: la ganancia de
   frecuencia (2.9 %) es del orden de la dispersión entre réplicas, mientras que
   la penalización por hazards (entre 6 % y 100 % de CPI) es de otro orden.
2. El pipeline sí gana en eficiencia de área: usa un 68 % menos de ALMs, un
   79 % menos de registros y duplica el throughput por mil ALMs.
3. La causa de que la ganancia de frecuencia sea pequeña es localizable: el
   lazo de resolución de ramas en EX. Resolver la rama en ID, o anticiparla,
   rompería ese lazo y dejaría el camino crítico en la lectura de la IMEM, con
   lo que el pipeline sí mostraría la ventaja de frecuencia que se le supone.

## 5. Advertencia sobre los datos de junio de 2026

Las réplicas de junio de 2026 (36.91 MHz y 56.61 MHz) no son comparables con
estas: eran de un RTL anterior al rediseño de la consola VGA, en el que las
memorias sombra de la consola no se inferían como M10K y el monociclo tenía
17 503 registros. Con esos datos la diferencia de Fmax a favor del pipeline era
del 53 % y el speedup llegaba a 1.23. La campaña actual sustituye esos números
por los del diseño que se va a documentar.
