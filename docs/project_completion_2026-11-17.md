# Estado de la revisión corregida

La corrección funcional está documentada en
[ADR 061](decisions/061_precise_synchronous_exceptions.md). Se aprobaron
268 pruebas sin fallos ni casos omitidos, incluidos los 60 programas de
`riscv-tests` en cada arquitectura. La unidad compartida de excepciones
y la retención de consumidores de resultados CSR resuelven los casos
antes registrados como fallos esperados. El alcance sigue limitado a
las condiciones ejecutadas y al entorno de modo máquina implementado.

Se completaron cinco compilaciones por arquitectura para caracterizar el
RTL corregido, con CoreMark de 2000 iteraciones como imagen de memoria.
Las diez aprobaron el análisis nominal de temporización. Se regeneraron
y aprobaron los seis programas de simulación por arquitectura, con
comparación de registros, memoria e instrucciones frente al modelo.

Las lecturas físicas de revisiones anteriores no validan estas fuentes.
La campaña física pendiente debe ejecutar cinco compilaciones del mismo
RTL con semillas distintas por programa y arquitectura, conforme al
anteproyecto. Se requieren 50 observaciones en total.

El plan puede generarse sin acceder a la placa.

```sh
.venv/bin/python3 scripts/measure_replica_campaign.py
```

La sesión física requiere la tarjeta encendida y una persona que lea
la consola VGA. La cadena RISC-V, Quartus y el entorno del proyecto
deben estar en `PATH`.

```sh
.venv/bin/python3 scripts/measure_replica_campaign.py --capture
```

Cada semilla se compila, se verifica y se programa antes de su lectura.
Se registran el estado `HALTED`, los contadores y el estado de salida
CRC de CoreMark. Para valores hexadecimales debe utilizarse `0x` al
introducirlos. Las observaciones se vinculan con el ejecutable, el
bitstream, la semilla y los informes de memoria y temporización.
Las compilaciones incompletas se archivan antes de regenerarse.

La comprobación de completitud no accede a la placa.

```sh
.venv/bin/python3 scripts/measure_replica_campaign.py --check
```

El generador estricto de informes utiliza ese mismo control. No acepta
cinco lecturas de una sola semilla como sustituto de cinco compilaciones.
El auxiliar `measure_physical_repetitions.py` estudia reinicios del mismo
bitstream y tiene un propósito distinto.

Una vez completada la campaña física se deben consolidar sus resultados
por programa y semilla y actualizar la comparación del manuscrito. Las
proyecciones de frecuencia máxima y los tiempos físicos deben permanecer
identificables por separado.
