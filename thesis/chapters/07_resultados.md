# Capítulo 7. Resultados

<!-- Generado por scripts/thesis_artifacts.py. Revisar y completar la interpretación antes de la entrega. -->

## 7.1 Resumen

Se compararon las dos microarquitecturas RV32IM sobre la FPGA Cyclone V DE1-SoC bajo el protocolo descrito en `docs/reproduction/`. El pipeline alcanzó una Fmax de 54.45 MHz ($\pm$ 0.78 MHz, n = 5) frente a los 52.92 MHz ($\pm$ 0.73 MHz, n = 5) del monociclo, es decir, una mejora de frecuencia de 2.9 %.

La mejora en frecuencia no se traslada sin más al rendimiento: el CPI del pipeline es mayor que uno en todos los programas medidos, porque cada burbuja de hazard y cada vaciado por rama tomada son ciclos perdidos. El resultado neto depende del balance entre la ganancia de reloj y la penalización por hazards.

## 7.2 Verificación funcional

Antes de medir el rendimiento se verificó la corrección funcional de ambas implementaciones contra el modelo de referencia de Python y contra la suite `riscv-tests`. La tabla `\ref{tab:verification_results}` resume el resultado.

## 7.3 Frecuencia máxima y recursos

La tabla `\ref{tab:fmax_replicas}` presenta la Fmax de cada réplica y la `\ref{tab:resources}` la utilización de recursos. La dispersión de la Fmax entre réplicas es comparable en las dos arquitecturas (CV 1.38 % en el monociclo y 1.43 % en el pipeline), de modo que la diferencia de Fmax entre los tratamientos (2.9 %) es mayor que la dispersión experimental y no es un artefacto del proceso de síntesis.

## 7.4 CPI, IPC y throughput

La tabla `\ref{tab:benchmarks}` muestra el CPI efectivo, el IPC y el throughput de cada programa. El monociclo presenta CPI = 1 en los programas sin división: cada ciclo retira una instrucción. La excepción es el programa de la extensión M, donde el divisor de 34 ciclos mantiene el datapath ocupado y el CPI del monociclo sube a 7.58. El pipeline retira una instrucción por ciclo en el mejor caso y pierde ciclos por hazard de datos, por vaciado de rama y por la latencia de la división.

## 7.5 Análisis estadístico

Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo. La desviación estándar de la Fmax es de 0.73 MHz en el monociclo (CV 1.38 %) y de 0.78 MHz en el pipeline (CV 1.43 %). La tabla `\ref{tab:statistics}` recoge la estadística completa.

## 7.6 Eficiencia relativa

La tabla `\ref{tab:efficiency}` contrasta el throughput con el costo en recursos. El pipeline es más barato en lógica y más caro en memoria: usa un 68 % menos de ALMs y un 79 % menos de registros, a cambio de un 13 % más de bloques RAM y un 43 % más de bloques DSP. Expresado en throughput por mil ALMs, el pipeline multiplica por 2.11 la eficiencia del monociclo. El intercambio entre rendimiento y área no es, por tanto, un compromiso equilibrado: en este diseño el pipeline gana en área y pierde en throughput.

## 7.7 Evaluación de la hipótesis

La hipótesis de trabajo $H_1$ no se sostiene en ninguno de los programas medidos: el extremo inferior de la dispersión del speedup queda por debajo de uno en todos los casos. La tabla `\ref{tab:speedup}` muestra el speedup del pipeline respecto al monociclo y su dispersión.

## 7.8 Discusión

El pipeline no supera al monociclo en ninguno de los programas medidos. La ganancia de frecuencia del pipeline es de 2.9 %, mientras que la penalización por hazards elevate el CPI del pipeline entre 6 % y 100 % respecto al monociclo: la segunda de las dos cantidades domina el resultado en todos los programas, de modo que la hipótesis de trabajo no queda sostenida y el mayor Fmax del pipeline no se traduce en mayor throughput.

## 7.9 Limitaciones

- El tamaño muestral ($n = 5$ réplicas) limita el análisis a la estadística descriptiva; no se aplican pruebas de significancia.
- El CPI se mide en simulación, no sobre la FPGA: es el mismo valor que congela el hardware, pero la variabilidad de la Fmax es la única fuente de dispersión considerada.
- CoreMark se mide con diez iteraciones para que la corrida termine en minutos; la mezcla de instrucciones, y por tanto el CPI, es la misma que con la corrida completa.
- CoreMark no cabe en la memoria de instrucciones de la FPGA, por lo que no se midió en hardware (ADR 042).
