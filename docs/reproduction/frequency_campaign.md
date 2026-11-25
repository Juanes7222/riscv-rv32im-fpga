# Campaña complementaria de frecuencia

La campaña caracteriza el mayor punto con cierre temporal y validación funcional por programa, arquitectura y semilla. La unidad experimental es una implementación nueva de Quartus para un punto de reloj. El ajuste de la PLL vuelve a ejecutar el Fitter, por lo que el resultado se limita a la rejilla y al flujo registrados. Las mediciones físicas originales a 40 y 50 MHz conservan su propia procedencia.

## Campaña completa

Desde Bash o WSL, con la DE1-SoC y VGA disponibles cuando se requieran lecturas:

```bash
make frequency-plan
make frequency-run
```

`frequency-plan` es de solo lectura. Audita las combinaciones disponibles en
`fc-seed1`, contrasta las entradas actuales con las archivadas, muestra las
combinaciones y arranques por completar y estima la concurrencia. La validación
de la versión instalada se realiza al iniciar. La planificación y las pruebas
pueden ejecutarse con Quartus y la tarjeta desconectados.

`frequency-run` inicializa o reanuda `fc-full`. Congela las entradas de las 50
combinaciones, incorpora los candidatos y arranques verificables de
`fc-seed1` y conserva el origen de cada artefacto. La versión requerida para
esta reutilización es Quartus Prime Lite 25.1std.0 build 1129 con cuatro
hilos de Fitter. Si varían la rejilla, las huellas de las entradas o la
versión, informa la incompatibilidad antes de combinar resultados. El
protocolo requiere 100 arranques válidos para 50 configuraciones y 25 pares.
Con la semilla 1 incorporada quedan 40 configuraciones y 80 arranques.

| Operación | Comando |
|---|---|
| Iniciar o reanudar | `make frequency-run` |
| Buscar sin operador o sin placa | `make frequency-run FREQUENCY_BOARD=0` |
| Acotar la concurrencia | `make frequency-run FREQUENCY_FULL_JOBS=2` |
| Seguir el progreso en otra terminal | `make frequency-progress FREQUENCY_ID=fc-full FREQUENCY_FOLLOW=1` |
| Solicitar una pausa ordenada | `make frequency-pause` |
| Auditar temporal y funcionalmente | `make frequency-status FREQUENCY_ID=fc-full` |
| Ejecutar únicamente la validación física elegible | `make frequency-observe-all FREQUENCY_ID=fc-full` |
| Generar el informe de candidatos | `make frequency-report FREQUENCY_ID=fc-full` |
| Regenerar el paquete académico | `make frequency-export` |
| Verificar paquete y evidencia | `make frequency-verify` |

La terminal muestra la preparación, la reutilización y el inicio y resultado
de cada candidato. Mientras hay trabajos activos, muestra cada 20 segundos
la frecuencia, el tiempo transcurrido, la etapa y la última línea del
registro de la herramienta. Durante una captura física, la salida de los
candidatos sigue en el archivo de sesión para dejar visibles las preguntas.
Consulta el progreso desde otra terminal. Con FREQUENCY_FOLLOW=1 se actualiza
cada 20 segundos y Ctrl+C cierra solo esa consulta.

En una terminal interactiva con JTAG disponible, el flujo presenta un
candidato cuando ya se han resuelto todos los puntos superiores. Identifica
el programa, la arquitectura, la semilla, la frecuencia y el arranque
pendiente. Pon la tarjeta en RUN, mantén KEY[0] y confirma el aviso de la
terminal. Suelta KEY[0] tras la confirmación de Quartus y sigue el procedimiento
de lectura de VGA. Las otras combinaciones siguen compilándose mientras se
espera la intervención. El registro persistente de compilaciones está bajo
`sessions/` y el operador recibe un solo aviso a la vez. Si el cable no
aparece al iniciar o la entrada no es interactiva, se completa el trabajo
temporal que se pueda y se difieren los arranques. Vuelve a ejecutar
`make frequency-run` cuando la placa y el operador estén disponibles.

`frequency-pause` señala al flujo en curso desde otra terminal. Los trabajos
activos disponen de 90 segundos para terminar y sellar su evidencia.
Al vencer ese plazo se detienen las herramientas pendientes y los intentos
se conservan con estado `interrupted`. Si el operador está ante un aviso para
programar, puede pulsar Enter para salir de esa espera tras haber solicitado
la pausa. Si ya soltó el reinicio, puede terminar la lectura actual.
Ctrl+C en el flujo integrado interrumpe la captura y aplica el mismo plazo
a los trabajos activos. Un arranque sin observación sellada se vuelve a
programar al reanudar.

Un registro de herramienta sin crecimiento durante 900 segundos queda como
`tool_timeout`. Estos estados son errores de infraestructura que mantienen
el punto pendiente. Al reanudar se usa el punto de restauración del Fitter
si existe y conserva sus huellas. Una violación temporal sellada se conserva
como evidencia. Los límites se ajustan con `FREQUENCY_PAUSE_GRACE_SECONDS` y
`FREQUENCY_TOOL_IDLE_SECONDS`. El cierre del proceso de Windows y la
exportación parcial pueden añadir tiempo al plazo de pausa.


La concurrencia automática reserva un procesador lógico para la interacción,
usa la memoria disponible de Linux/WSL como aproximación y limita el plan
a tres procesos. Si la memoria disponible no se conoce comienza con uno.
`FREQUENCY_FULL_JOBS` permite ajustarla sin afectar la identidad de los
artefactos. Cambiar los cuatro hilos del Fitter puede alterar el enrutamiento
e impide reutilizar la semilla 1. Cada compilación escribe en su propio
proyecto. Reserva espacio para todos los candidatos producidos y supervisa la
unidad con el plan. Una ejecución sobre Linux/WSL y otra nativa de Windows
en paralelo quedan fuera del protocolo de publicación y bloqueo de JTAG.

La semilla 1 registró medianas de 250 s para Quartus, 7,7 s para TimeQuest
nominal y 85 s para el barrido VGA tras pasar el análisis nominal. El flujo registra el
tiempo del operador y de la placa por separado en los arranques nuevos.
`sessions/*.json` registra tiempo transcurrido y espera por candidatos.
`data/results.json` incluye los tiempos acumulados por etapa, cuya suma
puede superar el tiempo real cuando existen trabajos concurrentes. La mejora
total del rendimiento del flujo se podrá medir al ejecutar las semillas
pendientes. Se conserva la compilación por ejecutable. Actualizar los MIF de
un SOF ajustado requeriría demostrar, por separado, la equivalencia de los
artefactos y de la unidad experimental.

## Exportación académica

```bash
make frequency-export FREQUENCY_ID=fc-seed1
make frequency-verify FREQUENCY_ID=fc-seed1
make frequency-export FREQUENCY_ID=fc-seed1 FREQUENCY_LATEX=pdflatex.exe
```

`frequency-run` exporta el estado alcanzado al finalizar la sesión. El
directorio `academic/` tiene el conjunto consolidado con su manifiesto
SHA-256, CSV de observaciones, candidatos y pares, fuentes LaTeX y PGFPlots
y `preview.tex`. Puede copiarse a otra máquina y validarse con
`make frequency-verify FREQUENCY_PORTABLE=1 FREQUENCY_OUTPUT=/ruta/del/paquete`.
Sin la opción portable se coteja también la evidencia original de la campaña.
Para compilar con TeX Live, usa `FREQUENCY_LATEX=pdflatex`. Con MiKTeX en WSL,
el directorio de exportación debe estar en una ruta visible desde Windows.
La exportación conserva las fuentes y el registro si falla LaTeX.

Incorpora las tablas y figuras con los comandos `\input{tables/...}` y
`\input{figures/...}`. Las tablas emplean `booktabs` y, para los anexos
largos, `longtable`. Las figuras emplean PGFPlots 1.18. Las comparaciones
identifican explícitamente las aceleraciones físicas originales, las
proyecciones históricas a Fmax restringida y las aceleraciones relativas a
las nuevas frecuencias validadas. Los resultados de una sola semilla cubren
5 de los 25 pares. El paquete incluye un veredicto descriptivo global solo
cuando existe la evidencia de todos los pares.

## Entradas y reloj

Se requiere GNU Make, Bash, Python 3.10 o posterior con las dependencias de `requirements.txt`, Git y Quartus Prime con soporte Cyclone V para `5CSEMA5F31C6`. El piloto utiliza Quartus Prime Lite 25.1std.0 build 1129. En WSL, mantén el repositorio en una unidad visible desde Windows y las herramientas de Quartus en PATH. Para indicar otras rutas, define `VENV_PY`, `QUARTUS_SH`, `QUARTUS_STA`, `QUARTUS_PGM` o `JTAGCONFIG` al llamar a Make.

`make frequency-init` crea un espacio independiente y congela el RTL, las restricciones, el pinout y las entradas de compilación. Obtiene el ELF, IMEM, DMEM y la plantilla de la consola de los archivos históricos de la combinación y comprueba sus SHA-256 contra el manifiesto original. Conserva la referencia funcional y la huella del SOF histórico. Cada candidato construye un proyecto local desde esas entradas. El procedimiento recompila por ELF y conserva `tohost=0x6000` para CoreMark y `0x708` para los sintéticos. Las profundidades físicas siguen siendo 4096 y 1024 palabras.

La referencia de ambos diseños es de 50 MHz. El monociclo usa la PLL de CPU existente y el segmentado activa una PLL de CPU para esta campaña, incluido el punto de 50 MHz. El segmentado conserva el reloj directo cuando se compila con el flujo histórico. VGA toma su reloj de su propia PLL, referida a la entrada de 50 MHz. La salida de la PLL de CPU se solicita con fase cero y ciclo de trabajo de 50 %. El reinicio se afirma asíncronamente y se libera en el dominio local cuando la PLL está bloqueada. El monociclo conserva las transferencias entre flancos de las memorias.

La rejilla inicial usa los enteros 40 a 49 MHz para el monociclo y 50 a 63 MHz para el segmentado. Para un objetivo entero (q), se escoge el mayor cociente realizable con contadores enteros y divisor de salida par en el intervalo ((q-1,q]) MHz. Se acota el PFD a 5–50 MHz y el VCO a 600–1600 MHz según el dispositivo y la referencia disponible. La búsqueda matemática ofrece un cociente para cada punto de la rejilla inicial. Quartus selecciona los contadores físicos y el postdivisor del VCO. El manifiesto guarda el cociente solicitado y la cadena ajustada que reporta TimeQuest. Se comprueban el cociente, el período, el flanco de subida y el de bajada con tolerancia de redondeo de 2 ps para la onda. Si el ajuste produce un cociente diferente, el punto queda indeterminado y requiere diagnóstico. La frecuencia utilizada en los cálculos procede de la cadena ajustada. Una medición externa del oscilador sería una variable adicional. [Cyclone V Device Datasheet, tabla 31](https://www.intel.com/programmable/technical-pdfs/683801.pdf)

## Compilación y selección

Desde la raíz del repositorio, con las dependencias en `.venv`:

```bash
make frequency-test
make frequency-init FREQUENCY_ID=mi-piloto
make frequency-search FREQUENCY_ID=mi-piloto FREQUENCY_JOBS=3
make frequency-status FREQUENCY_ID=mi-piloto
make frequency-report FREQUENCY_ID=mi-piloto
```

El piloto ya inicializado se llama `fc-pilot` y es el valor predeterminado de `FREQUENCY_ID`. Para continuarlo, ejecuta `make frequency-search`. Se repite el mismo comando después de una interrupción. `FREQUENCY_ARGS="--reuse-from ID"` permite conservar compilaciones de otra campaña si coinciden el candidato, la versión, los hilos, las huellas de las entradas de síntesis y las restricciones. Se vuelven a comprobar los informes y el SOF y se conserva el manifiesto de origen.

La búsqueda va de mayor a menor y mantiene la semilla fija. El planificador prioriza combinaciones independientes y da paso a las que han recibido menos compilaciones en la sesión. Cada combinación de arquitectura, programa y semilla mantiene como máximo un candidato activo. Las combinaciones independientes se ejecutan en paralelo. Cuando se confirma un punto, los inferiores esperan hasta que exista un fallo funcional verificado. Los errores de infraestructura permanecen sin resolver y se pueden reintentar al reanudar. Un fallo confirmado en placa permite que `make frequency-search` continúe hacia abajo. `FREQUENCY_JOBS` controla la cantidad de proyectos simultáneos y puede cambiarse al reanudar. `FREQUENCY_THREADS` fija los hilos de Quartus por proyecto al inicializar. En un equipo con 12 procesadores lógicos, `FREQUENCY_JOBS=2` reserva capacidad y `FREQUENCY_JOBS=3` permite usar los 12 hilos con el valor predeterminado de cuatro hilos por proyecto. El número de trabajos activos se mantiene dentro del límite configurado en todas las etapas. Se registran por separado los tiempos de preparación, Quartus, huellas de la base ajustada, TimeQuest, barrido VGA, verificación de memoria y sellado. Estos valores aparecen en el registro de búsqueda y en `reports/candidates.csv`. El perfil en `reports/report.json` agrega tiempos por fase de los candidatos nuevos. La suma de tiempos de los trabajos puede superar el tiempo de pared de la campaña porque se ejecutan en paralelo.

Un candidato con evidencia íntegra se reutiliza al reanudar. Cada intento queda en su propio directorio. Si la compilación terminó y su base ajustada conserva las huellas registradas, la recuperación vuelve a ejecutar TimeQuest sobre el SOF existente y conserva los análisis previos. Un error de ejecución, evidencia faltante o discrepancia de reloj deja el punto pendiente de resolver y bloquea la confirmación de cualquier máximo inferior. Si aprueba el extremo superior se informa que se alcanzó el límite de la rejilla.

El SDC conserva el reloj de entrada, los relojes derivados, la incertidumbre del dispositivo, las excepciones de reset y sincronizadores, el máximo de 10 ns del bus de captura y los presupuestos del DAC. TimeQuest analiza los modelos lento y rápido a 0 y 85 °C, a 1100 mV. Se requieren holguras no negativas de setup, hold, ancho de pulso, recuperación y remoción cuando hay rutas aplicables, los 25 endpoints del DAC, ambos enlaces de sincronismo del monitor y el bus CPU–VGA. Los informes de transferencias y metastabilidad se conservan junto con la cobertura de endpoints y la revisión de excepciones ignoradas. El reporte de transferencias enumera ambas direcciones de medio ciclo en el monociclo. Se conservan Fmax y Fmax restringida del reloj de CPU por cada modelo que las publica. Las holguras y la cobertura deciden la aceptación.

Los candidatos que superan el análisis nominal pasan también por el barrido histórico VGA de 120 casos. El presupuesto de ±0,5 ns debe cumplir para los modelos de carga del proyecto y de 10/10 pF. Se verifica que el cambio de carga altere el modelo y se conserva el barrido completo. Si el análisis nominal ya encuentra una violación, ese candidato se descarta y se ahorra el barrido. Por último se confrontan las imágenes de memoria compiladas mediante `check_mem_init.py`.

## Ejecución en la DE1-SoC

```bash
make frequency-jtag
make frequency-select ARCH=single_cycle
make frequency-program ARCH=single_cycle
```

`frequency-select` imprime frecuencia, ruta y SHA-256. `frequency-program` verifica y descarga inmediatamente el SOF seleccionado a la FPGA usando JTAG. Muestra la salida de Quartus a medida que avanza y guarda `program.log` en el directorio `programming/` del candidato. El éxito requiere que Quartus confirme `Configuration succeeded`. Para el segmentado, usa `ARCH=pipeline`. Los valores predeterminados son `FREQUENCY_CABLE=DE-SoC` y `FREQUENCY_DEVICE=2`. Si la cadena difiere, usa los valores que indica `make frequency-jtag`.

Usa `frequency-observe` una vez por arquitectura. Completa los arranques que falten hasta llegar a dos observaciones válidas. Cada arranque vuelve a descargar el SOF y guarda su propio log bajo `boots/`. Si interrumpes el comando, los arranques ya registrados se reutilizan al repetirlo.

1. Conecta VGA y pon la placa en RUN. Mantén KEY[0] presionado **antes de ejecutar** `make frequency-observe ARCH=single_cycle`. Mantén KEY[0] hasta que Quartus confirme la configuración. La descarga inicializa las memorias.
2. Con la programación terminada, suelta KEY[0] una vez y confirma en la terminal que se mantuvo presionado durante la descarga. Deja STEP y LOAD sin accionar. Espera que se estabilice VGA y confirma `HALTED=1`.
3. Lee `CyclesToPass`, `InstrToPass` y el estado de salida en la tabla de registros. Para CoreMark se lee x5/t0. Para los sintéticos se lee x10/a0, que conserva el valor escrito en `tohost`. Introduce el prefijo `0x` en lecturas hexadecimales, incluso cuando solo contienen dígitos. El estado de salida 1 y los contadores exactos son necesarios para aceptar. Consulta [el protocolo de CoreMark](coremark_physical_crc.md).
4. Si falta un arranque, la terminal te pide mantener KEY[0] presionado de nuevo y pulsar Enter para programar el siguiente. Al completar el monociclo, ejecuta `make frequency-observe ARCH=pipeline`. Usa `FREQUENCY_CAPTURE=RUTA` para archivar una foto. Si registras varias fotos en una misma sesión, actualiza el archivo con la captura del arranque en curso antes de terminar de introducir sus lecturas. Un fallo funcional exige dos lecturas coincidentes, revisadas y acompañadas de capturas.
5. Ejecuta `make frequency-report` para validar las lecturas de ambos arranques y actualizar el informe. Usa `make frequency-status` para ver el estado parcial.

Para la semilla 1 de CoreMark se esperan 627612883 ciclos en el monociclo (`0x25689cd3`), 802319745 en el segmentado (`0x2fd26d81`) y 627612849 instrucciones retiradas en ambos (`0x25689cb1`). La espera y la transcripción requieren un operador con acceso físico a la consola VGA. La programación, validación de evidencia y generación del informe se automatizan.

## Resultados y ampliación

`results/frequency_campaign/<id>/` contiene el manifiesto de campaña, estado, entradas congeladas, proyectos e informes. Cada candidato guarda sus intentos bajo `c/<programa>/<arquitectura>/s<semilla>/<MHz>/a<N>/`. El manifiesto de intento registra entradas, versión, cocientes de PLL, SOF y SHA-256, cierre temporal y motivo de decisión. Los arranques se registran dentro de `boots/`. `reports/candidates.csv` muestra ambos relojes nominales donde hay evidencia ajustada, Fmax, holguras y estado físico. `reports/report.json` muestra únicamente métricas obtenidas de candidatos seleccionados y observaciones físicas verificadas. Los resultados de esta campaña se guardan fuera de las rutas históricas.

El informe calcula CPI, IPC, tiempo nominal (C/f) e instrucciones por segundo. Empareja los tiempos por programa y semilla con el mismo ELF, calcula (S=T_m/T_s), (K=C_s/C_m) y (F=f_s/f_m), y resume las aceleraciones y la dispersión de frecuencias entre semillas. Considera empate (|S-1|\le 10^{-9}). La regla descriptiva requiere (\bar S-s>1) en al menos tres cargas, con todos los 25 pares disponibles. Las tablas parciales no emiten una conclusión para la hipótesis.

Para ampliar el piloto a las cinco cargas con la semilla 1:

```bash
make frequency-init FREQUENCY_ID=fc-seed1 FREQUENCY_PROGRAMS="coremark raw_stress load_use_stress branch_stress m_ext_stress"
make frequency-search FREQUENCY_ID=fc-seed1 FREQUENCY_REUSE_FROM=fc-pilot
make frequency-progress FREQUENCY_ID=fc-seed1
make frequency-status FREQUENCY_ID=fc-seed1
make frequency-observe-all FREQUENCY_ID=fc-seed1
make frequency-report FREQUENCY_ID=fc-seed1
```

`frequency-progress` lee los manifiestos y permite consultar la búsqueda sin repetir las comprobaciones de integridad. Para un estado auditado, usa `frequency-status`. La búsqueda conserva los candidatos reutilizados y los arranques auditados del piloto si coinciden las entradas, la versión, las frecuencias y el SOF. Los manifiestos y lecturas originales se archivan junto con la evidencia importada. El objetivo `frequency-observe-all` omite combinaciones ya validadas y las que aún requieren búsqueda temporal. Pide preparar KEY[0] antes de programar cada combinación y puede reanudarse repitiendo el comando. Cada ejecución de placa sigue requiriendo un operador para el reinicio y las lecturas.

Para programar o capturar una sola combinación usa `ARCH`, `PROGRAM` y, si corresponde, `FREQUENCY_SEED`. La ampliación a las semillas 2–5 requiere otro manifiesto y una ejecución autorizada aparte.

## Contraste con la campaña física original

Las cifras se verificaron tomando la última observación aceptada por programa, arquitectura y semilla, enlazando cada fila con su manifiesto de réplica y la tabla de Fmax del modelo lento a 85 °C. Cada CSV de CoreMark contiene una recaptura que comparte semilla con otra fila. Así se obtienen 25 implementaciones por arquitectura y 25 pares en total.

| Arquitectura | Fmax restringida mínima | Media | Máxima | CoreMark semilla 1 |
|---|---:|---:|---:|---:|
| Monociclo | 43,60 | 45,3348 | 47,47 | 45,03 |
| Segmentado | 55,62 | 59,7468 | 61,81 | 59,82 |

| Carga | Ciclos segmentado/monociclo | Aceleración nominal original | Proyección histórica a Fmax |
|---|---:|---:|---:|
| raw_stress | 1,1271 | 1,1091 | 1,1700 |
| load_use_stress | 1,8899 | 0,6614 | 0,6978 |
| branch_stress | 1,5001 | 0,8333 | 0,8791 |
| m_ext_stress | 1,0281 | 1,2159 | 1,2827 |
| coremark | 1,2784 | 0,9778 | 1,0307 |

Los CSV históricos conservan el reloj nominal original de 40 y 50 MHz. Para regenerar su informe estricto se debe usar la revisión histórica que corresponde a las huellas originales ya que el informe estricto comprueba la coincidencia con el RTL del checkout.
