# Revisión de resultados y cumplimiento del documento final

Fecha: 2026-11-12. Documento rector: `../ProyectoGrado/main.tex`, sus capítulos
y `../ProyectoGrado/out_dir/main.pdf`, de 183 páginas. Se prioriza el alcance
de la versión final, especialmente objetivos y §3.8 de revisión del protocolo;
no se exige retrospectivamente el protocolo más amplio del anteproyecto.

## Dictamen

La implementación y la campaña aportan evidencia suficiente para sostener una
comparación experimental acotada. La lectura incoherente de instrucciones se
resolvió con una nueva captura física del 12 de noviembre. La entrega aún no
está cerrada: el documento presenta datos anteriores y falta acreditar el
cierre temporal con las restricciones de los
relojes físicos. También falta incorporar evidencia visual del uso docente y
sincronizar la copia del código distribuida con la tesis.

Que el pipeline no supere al monociclo en CoreMark a 40/50 MHz no constituye un
incumplimiento del objetivo de determinar el efecto de la segmentación. El
resultado puede ser negativo o depender de la carga. No hace falta rediseñar
el procesador para forzar una victoria del pipeline.

Esta revisión no cambia RTL, scripts ni las mediciones originales. La captura
nueva del autor se añadió al historial y confirma la coherencia del retiro.

## 1. Evidencia que ya mejoró y es aprovechable

- Los XML y el informe conservan 250 ejecuciones sin fallos inesperados:
  162 para monociclo y 88 para pipeline. No equivalen a 250 pruebas de
  conformidad ISA independientes: incluyen los fallos esperados de los wrappers.
- Los doce casos de benchmark en simulación tienen resultado `pass`, evidencia
  diferencial válida y comparación de los 32 registros y 32768 bytes de DMEM.
  Los CRC de CoreMark de 1 y 10 iteraciones también están registrados.
- Las diez réplicas actuales incluyen `manifest.json`, `timing.rpt`,
  `fit.summary`, `compile.log`, bitstream e `inputs.tar.gz`. Comparten huella
  RTL y el ELF físico corregido de 2000 iteraciones, hash
  `1d99dfc60cdf9da2b89ede209f472cc66103f58ef476919381505086a308c481`.
- Los cuatro sintéticos medidos en cada arquitectura coinciden exactamente
  en ciclos e instrucciones con sus referencias de simulación y usan el mismo
  ELF correspondiente. Son ocho coincidencias físicas aprovechables.
- CoreMark registra `x5/t0=1` en ambas arquitecturas con el método
  `crc-gated-t0-v1`, observación JSON y hashes del programa, bitstream y log de
  verificación de IMEM. Es evidencia del resultado de los chequeos CRC; no es
  una captura de las palabras CRC individuales ni certificación de CoreMark.
- Los bitstreams de esas dos observaciones coinciden con la réplica 5 de cada
  arquitectura. No se encontró una ejecución física documentada de cada una
  de las otras cuatro réplicas; esto debe expresarse como alcance de la
  campaña, sin convertir cinco síntesis en cinco mediciones físicas.
- `scripts/generate_reports.py --check` pasó sus 16 comprobaciones. La función
  actual `evidence_issues` devolvió una lista vacía. Esto comprueba las reglas
  implementadas y la integridad del paquete, pero no detectó la incoherencia
  de transcripción documentada en la sección siguiente.

## 2. Resuelto: instrucciones de CoreMark monociclo

Actualización posterior a la revisión inicial: la captura de
`2026-11-12T12:45:14.321935+00:00`, conservada en la fila 4 del CSV monociclo,
registra `CyclesToPass=0x25689CD3`, `InstrToPass=0x25689CB1` y `x5/t0=1`.
Se comprobó su observación y la procedencia archivada. Los valores vigentes son:

| Dato confirmado | Monociclo | Pipeline |
|---|---:|---:|
| Ciclos | 627612883 | 802319745 |
| Instrucciones | 627612849 | 627612849 |
| CPI calculado | 1.0000000542 | 1.2783673028 |
| Estado CRC observado | 1 | 1 |

Los dos conteos de instrucciones coinciden. En monociclo hay 34 ciclos
adicionales respecto al retiro; no se registra un CPI de 15.9448 en la nueva
captura. La fila anterior permanece como antecedente y no se modifica su JSON.
La nueva lectura elimina este bloqueo experimental; sigue siendo recomendable
añadir al capturador la comprobación de coherencia que habría detectado el dato
anterior antes de publicarlo.

Se ejecutó `make validate-campaign` después de esta captura. El paquete se
regeneró en estado `checked`, con ambos conteos de instrucciones iguales y
sus 16 comprobaciones de tablas y figuras aprobadas. Esto no actualiza por sí
solo el documento `ProyectoGrado` ni sustituye el análisis temporal pendiente.

### Hallazgo original y trazabilidad

Fuente: `results/hardware_single_cycle_coremark_v2.csv:3` y su observación JSON.

| Dato registrado | Monociclo | Pipeline |
|---|---:|---:|
| Iteraciones | 2000 | 2000 |
| Ciclos | 627612883 | 802319745 |
| Instrucciones | 39361713 | 627612849 |
| CPI | 15.9448 | 1.2784 |
| ELF | Mismo hash | Mismo hash |
| Resultado del chequeo CRC | Éxito observado | Éxito observado |

La lectura monociclo no es coherente con la ejecución de la misma carga y la
ventana de retiro homogénea. Además, sus ciclos menos 34 dan 627612849, el
conteo registrado por el pipeline. La comparación hexadecimal es sugerente:

- Registro anterior: `0x02589CB1` = 39361713.
- Valor compatible con los otros dos datos: `0x25689CB1` = 627612849.

La omisión de un dígito `6` es una hipótesis de transcripción, no una causa
demostrada. No se debe sustituir automáticamente el número ni editar el JSON
sellado para hacerlo coincidir. El autor indicó que no conservaba la lectura
original y repitió la medición, conservando ambas filas.

Comando existente para recapturar únicamente esa carga:

```sh
make measure-hardware ARCH=single_cycle ELF=build/coremark/coremark.elf FORCE=1
```

`FORCE=1` es necesario porque el registro anterior figuraba como aprobado y podía
ser reutilizado por la caché. Conviene conservar fotografía de los contadores
y x5/t0 e introducir los valores con prefijo `0x`.

La limitación del generador está localizada en
`scripts/coremark_hardware.py:86`: exige contadores positivos y comprueba
hashes y observación, pero no contrasta la coherencia de instrucciones entre
arquitecturas para el mismo ELF/protocolo. El dato erróneo aparece por ello
como aprobado en la versión previa de `build/reports/latest/report.md:40`.

Mejora necesaria del flujo: separar éxito funcional CRC de aceptación de la
medición de rendimiento y rechazar diferencias no justificadas de retiro
entre arquitecturas para una misma carga. Una copia coherente del mismo
error en CSV y JSON no constituye una comprobación independiente.

## 3. Resultados numéricos actuales

Fuentes: CSV del paquete `build/reports/latest/results/`, reconstruidos desde
los reportes de las cinco réplicas y los contadores originales.

| Indicador | Monociclo | Pipeline |
|---|---:|---:|
| Frecuencia máxima media | 48.244 MHz | 63.886 MHz |
| Desviación muestral de frecuencia | 1.3958 MHz | 0.7374 MHz |
| CV de frecuencia | 2.893 % | 1.154 % |
| ALM medios | 3833.4 | 4511.4 |
| Registros medios | 4140.4 | 5144.6 |
| Bloques RAM | 60 | 60 |
| DSP | 10 | 10 |
| Reloj físico CPU | 40 MHz | 50 MHz |
| Tiempo de CoreMark según los ciclos registrados | 15.690322 s | 16.046395 s |

El pipeline tiene 32.42 % más frecuencia máxima media, 17.69 % más ALM y
24.25 % más registros. La aceleración temporal de CoreMark a los relojes
físicos es 0.977810: aproximadamente 2.22 % menos iteraciones por segundo.
Este cálculo usa ciclos/reloj y no depende del conteo de instrucciones
inicialmente cuestionado y ya confirmado por la nueva captura. Las lecturas
manuales requieren conservar su respaldo.

Las proyecciones emparejadas a frecuencia máxima muestran:

| Programa | Aceleración temporal media | Interpretación |
|---|---:|---|
| RAW | 1.1760 | Ventaja del pipeline |
| Extensión M | 1.2893 | Ventaja del pipeline |
| Bifurcaciones | 0.8836 | Penalización del pipeline |
| Carga-uso | 0.7013 | Penalización del pipeline |
| CoreMark, 1 iteración | 1.0402 ± 0.0422 | Cercanía a paridad |
| CoreMark, 10 iteraciones | 1.0372 ± 0.0421 | Cercanía a paridad |

Estas son proyecciones a partir de síntesis y ciclos de simulación, no
ejecuciones físicas a frecuencia máxima. No contradicen la ligera desventaja
física a 40/50 MHz. En los dos CoreMark la media menos desviación no supera
uno; esa regla descriptiva no acredita una mejora robusta ni es un intervalo
de confianza. No corresponde mezclar estos escenarios en una conclusión única.

## 4. El documento final todavía no representa esta campaña

El PDF inspeccionado es del 9 de noviembre; la campaña física nueva tiene
registros del 12. Las fuentes de resultados y conclusiones también conservan
la revisión del día 9. La generación de `build/reports/latest` no modifica
automáticamente `ProyectoGrado`.

Ubicaciones prioritarias respecto a `../ProyectoGrado/`:

| Archivo y ubicación | Problema actual | Acción |
|---|---|---|
| `chapters/06_results.tex:183` | Frecuencias y medias de la campaña anterior | Sustituir tabla, figura y análisis desde la campaña elegida |
| `chapters/06_results.tex:317` | Recursos históricos | Actualizar medias, dispersiones y porcentajes |
| `chapters/06_results.tex:330` | Figura 6.2 y pie con 16.66 % y 21.56 % | Conservar el diseño y actualizar datos y pie |
| `chapters/06_results.tex:428` | Ciclos e instrucciones de benchmarks anteriores | Incorporar los contadores y protocolo actuales |
| `chapters/06_results.tex:598` | CoreMark físico anterior | Reemplazar con la captura monociclo ya confirmada y la del pipeline |
| `chapters/06_results.tex:932` | Explica que el pipeline excluye NOP legítimos | Actualizar para los bits de validez y frontera de retiro corregidos |
| `chapters/07_conclusions.tex:9` | 49.10/62.15 MHz y 3857.2/4499.8 ALM | Reescribir conclusiones desde los resultados actuales |
| `chapters/07_conclusions.tex:21` | CRC físico aún pendiente como limitación histórica | Describir el método físico nuevo y sus límites, tras corregir la captura |
| `chapters/07_conclusions.tex:27` | Cuatro pruebas diferenciales de monociclo como evidencia original | Separar la historia de los doce casos actuales con comparación de estado |
| `chapters/03_methodology.tex:571` | Reportes originales pendientes | Explicar cuáles son históricos y cuáles ya existen en la campaña nueva |
| `chapters/03_methodology.tex:685` | Adaptaciones y alcance de evidencia | Fijar protocolo efectivo y vincular la campaña final con sus hashes |

El capítulo de conclusiones ya está incluido y las cifras de pruebas 250,
162 y 88 están actualizadas: estos puntos de la auditoría previa no siguen
pendientes. El abstract describe el proyecto pero no expone sus principales
resultados cuantitativos; completarlo mejoraría la versión final.

La Figura 6.2 se revisó visualmente en la página física 152 del PDF, numerada
134. Las barras laterales y las etiquetas superiores tienen margen y no
presentan el solapamiento señalado antes. El problema pendiente es la campaña
numérica mostrada, no rehacer la distribución de las barras.

## 5. Temporización: comparativa y cierre físico son comprobaciones distintas

Los SDC actuales restringen el reloj de entrada a 10 ns. En la réplica 1
monociclo el reporte deriva 80 MHz para CPU y 148.5 MHz para VGA bajo esa
restricción, aunque físicamente se usan 40 y 74.25 MHz. El pipeline se analiza
con entrada a 100 MHz aunque opera a 50 MHz.

Los reportes conservan slack de setup negativo bajo ese objetivo agresivo;
por ejemplo, réplica 1: -7.827 ns en CPU monociclo y -5.644 ns en pipeline.
Eso no demuestra un fallo a 40/50 MHz. Tampoco acredita por sí solo cierre
temporal a los relojes físicos. El propio reporte, en la nota del resumen
Fmax, advierte que esa cifra ignora transferencias entre relojes distintos.

Los peores slacks de hold multicorner de las diez réplicas inspeccionadas
son positivos. Siguen presentes puertos sin restricciones y excepciones de
temporización entre CPU y VGA. Por ejemplo, el reporte de réplica 1 monociclo
enumera 7 entradas y 80 salidas sin restricciones. No todos esos puertos son
necesariamente críticos; deben clasificarse según su uso, y no ocultarse.

Acción de cierre: analizar las implementaciones correspondientes con el reloj
físico de entrada de 20 ns, conservar setup/hold y clasificación de rutas
no restringidas, y justificar los cruces CPU/VGA. Puede hacerse como análisis
de la implementación existente; no se deduce que sea preciso rehacer las
diez síntesis únicamente para cambiar la restricción de comprobación.

El `set_false_path` del SDC excluye rutas del análisis, pero no demuestra que
una captura multibit de VGA sea coherente. La tesis debe explicar la captura
estable de contadores y los mecanismos usados para estados docentes.

## 6. Matriz frente a los objetivos del documento final

Fuente: `chapters/01_introduction.tex:62` y siguientes.

| Objetivo | Evaluación | Cierre necesario |
|---|---|---|
| Implementar ambas microarquitecturas RV32IM y resolver riesgos | Implementación sustentada por RTL, síntesis y pruebas | Fijar la revisión que acompaña al documento |
| Verificar con riscv-tests y cocotb | Evidencia amplia y ampliada con comparación diferencial | Mantener alcance y fallos esperados explícitos; evitar confundir aprobación de wrappers con conformidad exhaustiva |
| Desarrollar visualización docente en DE1-SoC | Módulo implementado y utilizado para leer resultados físicos | Incorporar capturas del avance por etapas y un ejemplo de riesgo en modo paso, ligados a programa y bitstream |
| Comparar Fmax, CPI, throughput y recursos | Campaña numérica disponible, retiro confirmado y trazabilidad mejorada | Documentar cierre temporal y actualizar capítulo 6 |
| Objetivo general: determinar la mejora y su costo | La evidencia permite una respuesta dependiente de carga y reloj | Reescribir conclusiones con la campaña final y distinguir medición de proyección |

No se exige un estudio de usuarios del módulo docente porque el objetivo es
desarrollarlo, no demostrar experimentalmente una mejora pedagógica. Una
demostración documentada es suficiente para sustentar ese entregable.

El capítulo 5 distingue 37 pruebas RV32I y 8 de M por arquitectura, además
de las limitaciones de modo máquina. No conviene convertir las 7/8 discrepancias
de `rv32mi` en un requisito nuevo de certificación privilegiada ajeno al
alcance; sí debe mantenerse una matriz clara entre instrucciones, pruebas y
limitaciones para respaldar el uso de «RV32IM completo» en el objetivo.

## 7. Reproducibilidad y mejoras de entrega

La copia `ProyectoGrado/rv32im-pipeline-de1soc` sigue en la revisión
`e53e7bdc8b3443b4145a3dcd00a6e386ecfa5a3e`, mientras el repositorio revisado
está en `ef8b61105bc841cbc5efffc63cb7715e32a25e7f`. La copia incluida conserva
52.920 MHz y 11400 ALM para monociclo en `results_statistics.csv`; no representa
la campaña del informe actual ni las cifras del texto. Antes de entregar hay
que sincronizar y fijar la revisión correcta, conservando el trabajo local.

Solo se encontró el logotipo institucional como imagen raster en la carpeta
de figuras del documento. No se localizaron fotografías de la consola ni del
modo paso en las rutas inspeccionadas. Esto no demuestra que no existan fuera
de los repositorios: deben incorporarse si ya se tienen.

El log de LaTeX no muestra referencias bibliográficas o etiquetas pendientes
en la búsqueda realizada, pero conserva avisos de desbordamiento de contenido,
algunos de más de 80 puntos, y un aviso de bibliografía para el tipo `standard`.
Conviene revisar visualmente tablas/listados y completar la edición del PDF.

## Orden mínimo de cierre

1. **Completado:** repetir CoreMark monociclo y registrar una fila nueva con
   retiro coherente, conservando la fila anterior y sus archivos sellados.
2. Incorporar controles de coherencia de retiro en el capturador/generador.
3. Archivar el análisis temporal de los bitstreams con relojes físicos y
   justificar las excepciones y los cruces relevantes.
4. Sustituir datos, figuras, interpretación y conclusiones del documento por
   la misma campaña final, y reconstruir el PDF.
5. Incorporar la evidencia docente y fijar la copia del repositorio que se
   distribuye con la tesis.

Después de esos pasos, el trabajo puede defender la conclusión de que la
segmentación aumenta la frecuencia máxima y el costo de recursos, sin una
mejora uniforme del tiempo de ejecución. No se requiere una nueva arquitectura
ni ganar en CoreMark para que esa conclusión cumpla el objetivo experimental.
