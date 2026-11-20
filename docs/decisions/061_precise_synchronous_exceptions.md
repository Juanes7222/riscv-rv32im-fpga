# ADR 061. Excepciones síncronas y dependencias de resultados CSR

Estado aceptado el 17 de noviembre de 2026 para la revisión corregida.

## Evidencia

La campaña anterior aprobaba 37 programas de `rv32ui` y ocho de `rv32um`
por arquitectura. Los envoltorios de `rv32mi` reconocían siete fallos
esperados en monociclo y ocho en segmentada. Ese reconocimiento permitía
que la suite terminara sin fallos inesperados, pero no demostraba
corrección de esos comportamientos.

Los casos reproducían problemas de codificaciones ilegales, `EBREAK`,
alineación y una dependencia de datos de un resultado CSR en la
arquitectura segmentada. El último caso requería esperar el valor
que la instrucción CSR entrega al banco de registros en WB. No bastaba
con describirlo como una dependencia entre dos registros CSR.

## Decisión

Una unidad compartida identifica codificaciones no admitidas y las
excepciones síncronas implementadas. Se distinguen las causas de dirección
de instrucción desalineada, instrucción ilegal, punto de interrupción,
llamada desde máquina y accesos de carga o almacenamiento desalineados.
Se conservan causa, dirección de la instrucción y valor asociado hasta
actualizar `mcause`, `mepc` y `mtval`.

El entorno implementa exclusivamente modo máquina. `mstatus.MPP` conserva
ese modo, coherente con los niveles declarados en `misa`. `MRET` restaura
los bits de habilitación previstos por ese entorno. No se declara soporte
de usuario ni supervisor.

La instrucción que provoca la excepción no escribe el banco de registros,
la memoria ni los CSR como una operación ordinaria y no incrementa el
contador de instrucciones retiradas. El contador de ciclos sí incluye el
tiempo transcurrido. La segmentada confirma la excepción en WB, descarta
las instrucciones posteriores e impide que una escritura más joven en MEM
modifique la memoria o la sombra VGA en el mismo ciclo. La redirección
tiene prioridad frente a una división más joven, que se cancela.

Los resultados CSR se consideran disponibles en WB. Se retienen los
consumidores mientras la instrucción productora permanece en EX o MEM.
El monitor de `tohost` aplica la misma validez que la escritura efectiva
de memoria para ignorar una escritura descartada por la redirección.

## Comprobación y límites

Los 15 programas de `rv32mi` deben aprobar realmente en cada arquitectura.
Se eliminaron las condiciones que aceptaban sus fallos como resultado
esperado. Nueve pruebas dirigidas por arquitectura comprueban la causa,
`mepc`, `mtval`, la ausencia de efectos indebidos y los conflictos de una
excepción anterior con una división o una escritura a `tohost` posterior.
Se ejecutan además las suites completas de regresión.

Superar esos programas no demuestra conformidad exhaustiva con la
arquitectura privilegiada. No se implementa una comprobación completa
de permisos o existencia de todos los CSR ni se amplían aquí los
contadores arquitectónicos. Las pruebas de modos no disponibles pueden
omitir sus secuencias conforme a `misa` y `mstatus`.

## Consecuencias experimentales

Los informes y lecturas de la revisión anterior se conservan como evidencia
histórica. No validan el RTL corregido. Se deben regenerar las cinco
compilaciones por arquitectura, los conteos de los programas y las
observaciones físicas antes de sustituir la comparación de desempeño.
Cinco semillas físicas de implementación y cinco ejecuciones repetidas
en placa representan fuentes distintas de variación.
