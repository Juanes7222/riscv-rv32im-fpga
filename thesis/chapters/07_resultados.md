# Capítulo 7. Resultados

<!-- Generado por scripts/thesis_artifacts.py. Revisar y completar la interpretación antes de la entrega. -->

## 7.1 Resumen

Se compararon las dos microarquitecturas RV32IM sobre la FPGA Cyclone V DE1-SoC bajo el protocolo descrito en `docs/reproduction/`. El pipeline alcanzó una Fmax de 62.15 MHz ($\pm$ 1.03 MHz, n = 5) frente a los 49.10 MHz ($\pm$ 1.35 MHz, n = 5) del monociclo, es decir, una mejora de frecuencia de 26.6 %.

La mejora en frecuencia no se traslada sin más al rendimiento: el CPI del pipeline es mayor que uno en todos los programas medidos, porque cada burbuja de hazard y cada vaciado por rama tomada son ciclos perdidos. El resultado neto depende del balance entre la ganancia de reloj y la penalización por hazards.

## 7.2 Verificación funcional

Antes de medir el rendimiento se verificó la corrección funcional de ambas implementaciones contra el modelo de referencia de Python y contra la suite `riscv-tests`. La tabla `\ref{tab:verification_results}` resume el resultado.

## 7.3 Frecuencia máxima y recursos

La tabla `\ref{tab:fmax_replicas}` presenta la Fmax de cada réplica y la `\ref{tab:resources}` la utilización de recursos. La dispersión de la Fmax entre réplicas es comparable en las dos arquitecturas (CV 2.74 % en el monociclo y 1.66 % en el pipeline), de modo que la diferencia de Fmax entre los tratamientos (26.6 %) es mayor que la dispersión experimental y no es un artefacto del proceso de síntesis.

## 7.4 CPI, IPC y throughput

La tabla `\ref{tab:benchmarks}` muestra el CPI efectivo, el IPC y el throughput de cada programa. El monociclo presenta CPI = 1 en los programas sin división: cada ciclo retira una instrucción. La excepción es el programa de la extensión M, donde el divisor de 34 ciclos mantiene el datapath ocupado y el CPI del monociclo sube a 7.58. El pipeline retira una instrucción por ciclo en el mejor caso y pierde ciclos por hazard de datos, por vaciado de rama y por la latencia de la división.

### CoreMark en hardware

CoreMark es la carga de referencia del anteproyecto (sección 9.2.13), y su regla de ejecución exige al menos 10 s, de modo que la corrida oficial en la FPGA usa 2000 iteraciones y no las diez de la simulación. El programa ocupa 9044 bytes de la memoria de instrucciones (55 % de los 16 KB) y 3389 bytes del bloque de datos (83 % de los 4 KB), así que cabe en el dispositivo.

| Arquitectura | Reloj (MHz) | Ciclos | Instrucciones | Tiempo (s) | CoreMark | CoreMark/MHz |
|---|---|---|---|---|---|---|
| Monociclo | 40 | 627612772 | 627612738 | 15.69 | 127.47 | 3.187 |
| Pipeline | 50 | 802319073 | 627612245 | 16.05 | 124.64 | 2.493 |

La tabla `\ref{tab:coremark}` recoge la corrida; los ciclos y las instrucciones son los contadores congelados que se leyeron en la consola VGA. El monociclo rinde 3.19 CoreMark/MHz y el pipeline 2.49: la normalización por frecuencia aísla el efecto del CPI, que es la variable arquitectural que el benchmark mide.

## 7.5 Análisis estadístico

Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo. La desviación estándar de la Fmax es de 1.35 MHz en el monociclo (CV 2.74 %) y de 1.03 MHz en el pipeline (CV 1.66 %). La tabla `\ref{tab:statistics}` recoge la estadística completa.

## 7.6 Eficiencia relativa

La tabla `\ref{tab:efficiency}` contrasta el throughput con el costo en recursos. Respecto al monociclo, el pipeline usa un 16.7 % más de ALMs, un 21.6 % más de registros, sin cambio en bloques RAM y sin cambio en bloques DSP. Expresado en throughput por mil ALMs, el pipeline multiplica por 0.80 la eficiencia del monociclo. El intercambio no compensa: el pipeline consume más área y entrega menos throughput, de modo que su eficiencia por ALM es inferior a la del monociclo.

## 7.7 Evaluación de la hipótesis

La hipótesis de trabajo $H_1$ se sostiene solo en los programas `m_ext_stress`, `raw_stress` y no se descarta en los programas `branch_stress`, `coremark_iter1`, `coremark_iter10`, `load_use_stress`; en conjunto, el resultado es un rechazo parcial de la hipótesis, no una confirmación. La tabla `\ref{tab:speedup}` muestra el speedup del pipeline respecto al monociclo y el extremo inferior de su dispersión.

## 7.8 Discusión

El resultado es un rechazo parcial de la hipótesis de trabajo $H_1$: el pipeline supera al monociclo en `m_ext_stress`, `raw_stress` y pierde en `branch_stress`, `coremark_iter1`, `coremark_iter10`, `load_use_stress`. La ganancia de frecuencia (26.6 %) no compensa el aumento del CPI por hazard de datos, vaciado de las ramas tomadas y latencia de la división, que va de 3 % a 89 % según el programa. La ventaja se limita, por tanto, a las cargas intensivas en multiplicación y división y con pocas dependencias; no es una propiedad general de la microarquitectura. En la carga estándar CoreMark el pipeline rinde 2.49 CoreMark/MHz frente a 3.19 del monociclo, la métrica normalizada por frecuencia que recomienda EEMBC (sección 9.2.13).

## 7.9 Limitaciones

- El tamaño muestral ($n = 5$ réplicas) limita el análisis a la estadística descriptiva; no se aplican pruebas de significancia.
- El CPI se mide con los contadores del procesador en cocotb y se verifica sobre la FPGA con CoreMark (ADR 051). Los contadores son deterministas, así que la única fuente de dispersión que se modela estadísticamente es la Fmax.
- CoreMark se mide en simulación con diez iteraciones para el CPI; la corrida oficial en hardware usa 2000 iteraciones para cumplir el mínimo de 10 s de EEMBC y se ejecuta una vez por arquitectura, porque el conteo de ciclos no depende del seed de place-and-route.
