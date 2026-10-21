# Capítulo 7. Resultados

<!-- Generado por scripts/thesis_artifacts.py. Revisar y completar la interpretación antes de la entrega. -->

> **Aviso:** las réplicas de síntesis guardadas no corresponden a la versión vigente del RTL (huella `59eb2d651661`). Ejecute `make thesis` para repetirlas antes de consignar estos números.

## 7.1 Resumen

Se compararon las dos microarquitecturas RV32IM sobre la FPGA Cyclone V DE1-SoC bajo el protocolo descrito en `docs/reproduction/`. El pipeline alcanzó una Fmax de 56.61 MHz ($\pm$ 2.10 MHz, n = 5) frente a los 36.91 MHz ($\pm$ 0.26 MHz, n = 5) del monociclo, es decir, una mejora de frecuencia de 53.4 %.

La mejora en frecuencia no se traslada sin más al rendimiento: el CPI del pipeline es mayor que uno en todos los programas medidos, porque cada burbuja de hazard y cada vaciado por rama tomada son ciclos perdidos. El resultado neto depende del balance entre la ganancia de reloj y la penalización por hazards.

## 7.2 Verificación funcional

Antes de medir el rendimiento se verificó la corrección funcional de ambas implementaciones contra el modelo de referencia de Python y contra la suite `riscv-tests`. La tabla `\ref{tab:verification_results}` resume el resultado.

## 7.3 Frecuencia máxima y recursos

La tabla `\ref{tab:fmax_replicas}` presenta la Fmax de cada réplica y la `\ref{tab:resources}` la utilización de recursos. La dispersión de la Fmax entre réplicas es baja en el monociclo y moderada en el pipeline, lo que es coherente con la mayor libertad de placement que deja una ruta crítica repartida en cinco etapas.

## 7.4 CPI, IPC y throughput

La tabla `\ref{tab:benchmarks}` muestra el CPI efectivo, el IPC y el throughput de cada programa. El monociclo presenta CPI = 1 en los programas sin división: cada ciclo retira una instrucción. La excepción es el programa de la extensión M, donde el divisor de 34 ciceles mantiene el datapath ocupado y el CPI del monociclo sube a 7.58. El pipeline retira una instrucción por ciclo en el mejor caso y pierde ciclos por hazard de datos, por vaciado de rama y por la latencia de la división.

## 7.5 Análisis estadístico

Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo. La desviación estándar de la Fmax es de 0.26 MHz en el monociclo (CV 0.69 %) y de 2.10 MHz en el pipeline (CV 3.71 %). La tabla `\ref{tab:statistics}` recoge la estadística completa.

## 7.6 Eficiencia relativa

La tabla `\ref{tab:efficiency}` contrasta el throughput con el costo en recursos. El pipeline mejora el throughput con un número de recursos que depende del tipo de recurso considerado, de modo que la evaluación del intercambio entre rendimiento y área debe hacerse recurso a recurso.

## 7.7 Evaluación de la hipótesis

La hipótesis de trabajo $H_1$ se sostiene en los programas `coremark_iter1`, `coremark_iter10`, `m_ext_stress`, `raw_stress` y no se descarta en los programas `branch_stress`, `load_use_stress`. La tabla `\ref{tab:speedup}` muestra el speedup del pipeline respecto al monociclo y el extremo inferior de su dispersión.

## 7.8 Discusión

El resultado no es uniforme: el pipeline supera al monociclo en los programas `coremark_iter1`, `coremark_iter10`, `m_ext_stress`, `raw_stress` y no lo hace en `branch_stress`, `load_use_stress`. La ganancia de reloj se compensa con la penalización por hazards de datos, por el vaciado de las ramas tomadas y por la latencia de la división, de modo que la hipótesis de trabajo, enunciada de forma general, queda confirmada solo bajo la condición de carga del programa medido: es un resultado condicional, no una propiedad de la microarquitectura.

## 7.9 Limitaciones

- El tamaño muestral ($n = 5$ réplicas) limita el análisis a la estadística descriptiva; no se aplican pruebas de significancia.
- El CPI se mide en simulación, no sobre la FPGA: es el mismo valor que congela el hardware, pero la variabilidad de la Fmax es la única fuente de dispersión considerada.
- CoreMark se mide con diez iteraciones para que la corrida termine en minutos; la mezcla de instrucciones, y por tanto el CPI, es la misma que con la corrida completa.
- CoreMark no cabe en la memoria de instrucciones de la FPGA, por lo que no se midió en hardware (ADR 042).
