# Generación de reportes, tablas y figuras

El punto de entrada es `scripts/generate_reports.py`. Reutiliza los lectores
de `collect_results.py` y los cálculos y renderizadores de
`thesis_artifacts.py`. El Makefile ejecuta el mismo flujo en ambos casos:

```sh
make report          # ejecuta las suites y genera el informe
make report-quick    # genera el informe con los archivos disponibles
make check-artifacts # comprueba entradas, métricas, tablas y figuras
```

El resultado se publica en `build/reports/latest/`:

| Ruta | Contenido |
|---|---|
| `report.md` | Resumen de verificación, síntesis y comparación temporal; incidencias de evidencia |
| `results/` | Contadores originales usados y CSV derivados, incluida verificación |
| `thesis/tables/` | Tablas LaTeX generadas |
| `thesis/figures/diagrams/` | Figuras pgfplots, fuentes standalone y PDF |
| `manifest.json` | Estado del informe y hashes de entradas y salidas |

`REPORT_DIR` permite elegir otra carpeta de salida. Por defecto, ambos comandos
compilan las cinco figuras con `pdflatex.exe` en WSL o `pdflatex` en Linux.
Se requiere una instalación TeX con pgfplots, standalone, siunitx y lmodern.
Para generar únicamente CSV y fuentes LaTeX:

```sh
make report-quick REPORT_FLAGS=
```

## Entradas y separación de responsabilidades

- La verificación se obtiene de los XML de `verification/cocotb`. Un XML
  reciente, incluso fallido, tiene prioridad sobre una copia archivada. Las
  suites adicionales no se descartan por no estar en una lista de presentación.
- La síntesis comparativa se calcula con las réplicas de `results/<arch>/`.
  No se mezclan sus medias de frecuencia con los recursos de otra compilación.
- Los ciclos e instrucciones proceden de `results/results_benchmarks.csv`.
  CPI, IPC y rendimiento se recalculan con los enteros originales. El speedup
  temporal empareja semillas presentes en ambas arquitecturas.
- CoreMark se lee de `results/results_coremark.csv` y se deriva en la carpeta
  del informe. El generador no reescribe su entrada ni la campaña original.
- Los reportes exportados de caminos críticos son opcionales y deben
  identificarse con su implementación; una coincidencia de frecuencia no
  demuestra por sí sola su procedencia.

`collect_results.py` sigue disponible para diagnóstico independiente de los
proyectos de Quartus. Su CSV de la compilación de referencia se llama ahora
`results_synthesis_latest.csv`, para distinguirlo de una síntesis de campaña.
El comando `scripts/thesis_artifacts.py` delega en el generador unificado y
acepta sus mismos argumentos.

## Comprobaciones antes de publicar

La generación se hace en una carpeta temporal. Antes de sustituir el informe
anterior se comprueban los cálculos desde los contadores y réplicas, su
correspondencia con las tablas y figuras y, cuando se solicita, la compilación
real de los PDF. También se comprueba que las entradas no hayan cambiado
durante el proceso. Si falla algo, se conserva el informe anterior. Cada
sustitución correcta mantiene una copia `latest.previous-*`.

Los valores ausentes se muestran como ausentes: no se dibujan como recursos
o rendimiento igual a cero. Un benchmark fallido o sin instrucciones válidas
no participa en throughput ni speedup. Sus contadores y estado permanecen
visibles para diagnóstico. Las tablas opcionales desaparecen de la nueva
salida cuando ya no existe su entrada.

`make check-artifacts` verifica los hashes y vuelve a comprobar las métricas.
Cambiar las entradas después de generar el informe lo invalida. No basta con
que un número incorrecto se repita de forma consistente en CSV y figura.

## Estado diagnóstico y uso en la tesis

Un paquete puede ser numéricamente coherente y seguir teniendo evidencia
incompleta. Por eso el manifiesto y el informe enumeran réplicas sin procedencia
verificable, ventanas de retiro históricas, suites ausentes y CRC pendientes.
Las métricas basadas en frecuencia máxima se identifican como proyecciones.

Para rechazar esa evidencia antes de generar un informe de campaña:

```sh
.venv/bin/python3 scripts/generate_reports.py --strict --render
```

La etapa `artifacts` de `run_experiment.py` utiliza este modo por defecto.
`--report-mode diagnostic` permite solicitar explícitamente un informe
preliminar que enumere la evidencia pendiente. Un fallo de pruebas, de cálculo
o de compilación sigue siendo un error en ambos modos.

## Orden de la campaña y CRC físicos pendientes

`make thesis` y `make thesis-quick` generan un paquete preliminar. Que terminen
correctamente acredita la ejecución automatizada y la consistencia de sus
artefactos; el estado del informe indica si falta evidencia experimental.

`make full-campaign` ejecuta, en este orden:

1. La campaña automatizada y el informe preliminar.
2. La comprobación de CoreMark de `verify-coremark`.
3. Las mediciones físicas pendientes.
4. `make validate-campaign`: generación estricta del informe y comprobación de
   sus artefactos.

Los smoke tests conservan sus XML en `results/coremark_smoke_<arch>.xml`, sin
sobrescribir los `verification/cocotb/<arch>/results.xml` de las suites ISA.

La validación estricta se hace después de la captura física. Antes se exigían
los CRC físicos dentro de `thesis`, lo que impedía llegar a la etapa que mide
la FPGA. El nuevo orden no convierte un CRC simulado en evidencia física ni
marca automáticamente como validadas las lecturas de contadores.

El capturador `hardware_measure.py` actual registra ciclos e instrucciones;
para CoreMark conserva el estado `terminated-unvalidated` y `CRC pending`.
Esas lecturas por sí solas no eliminan el pendiente de CRC del informe.
`results/results_coremark.csv` es la entrada de las ejecuciones físicas para
el generador; sus filas históricas carecen de `coremark_functional_valid`.
Ese campo debe corresponder a una validación física documentada, no añadirse
para hacer pasar el comando. Si falta esa evidencia, el último paso de
`full-campaign` seguirá rechazando la publicación como validada.

Para regenerar las tablas y figuras disponibles sin repetir síntesis ni
simulaciones, usar `make report-quick`. Una vez registrada toda la evidencia,
`make validate-campaign` repite únicamente la comprobación final.

Los capítulos de `ProyectoGrado` contienen tablas y figuras propias: generar
este paquete no actualiza automáticamente toda su prosa ni sus tablas
incrustadas. Debe incorporarse la campaña seleccionada y revisar las
afirmaciones del capítulo. Para la Figura 6.2 se aplicó la fuente standalone
de recursos y su PDF al documento, conservando los valores históricos.

La gráfica de recursos presenta ALM y registros; RAM, DSP, memoria y pines
permanecen en su tabla. Las barras tienen espacio lateral explícito y margen
superior para sus valores. Las figuras por benchmark rotan las etiquetas
largas para evitar solapamientos.

## Pruebas de los generadores

```sh
.venv/bin/python3 -m unittest \
  verification/test_report_generation.py \
  verification/test_campaign_integrity.py \
  verification/test_campaign_order.py
```

Cubren selección de XML reciente, conservación de entradas, rechazo de
duplicados, fallos con cero instrucciones, recursos ausentes y DSP realmente
igual a cero, réplicas con huecos, eliminación de tablas opcionales obsoletas,
fallos de compilación, publicación y detección de resúmenes alterados.
