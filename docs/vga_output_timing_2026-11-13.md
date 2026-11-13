# Corrección de la interfaz VGA

Se registraron las salidas de vídeo de ambas arquitecturas y se definieron
sus restricciones temporales. Los informes de TimeQuest pasan de 28 salidas
VGA sin restricciones a cero. La decisión y sus hipótesis están en
[ADR 059](decisions/059_vga_output_timing.md).

## Comportamiento corregido

El registro de colores actualiza sus datos en el flanco ascendente del reloj
de píxel. El reloj enviado al ADV7123 se invierte: su flanco ascendente queda
medio período después de esa actualización. El borrado y los sincronismos
se retrasan para acompañar los dos ciclos del generador de texto y el nuevo
registro de salida. Se conserva el formato de barrido de 1650 por 750 posiciones,
con una región visible de 1280 por 720 píxeles y sincronismos positivos.

Las 24 señales de color y `vga_blank_n` usan los requisitos de establecimiento
y retención del DAC a 3,3 V. `vga_clock` es un reloj generado con destino en
su puerto físico; el informe incluye su recorrido hasta ese pin. H/V llegan
directamente al monitor y tienen un límite independiente de latencia de un
período de píxel, en lugar de requisitos de captura del DAC.

El desfase externo entre datos y reloj tiene un presupuesto de diseño de
±0,5 ns. No es un dato medido ni extraído de las pistas de la FPGA DE1-SoC.
Con los requisitos de 0,2 ns de establecimiento y 1,5 ns de retención del
[ADV7123, tabla 6](https://www.analog.com/media/en/technical-documentation/data-sheets/adv7123.pdf),
los retardos externos son `-max 0.700` y `-min -2.000`, en ns.

## Evidencia

Base: revisión `607043b`. Se compilaron ambos diseños con Quartus Prime
25.1std.0, semilla 5, memorias de instrucciones/datos de 4096/1024 palabras
y `TOHOST_ADDR=0x6000`. Los SDC de ambas arquitecturas son idénticos.
El PLL existente produce aproximadamente 74,24 MHz (período de 13,469 ns),
con una separación nominal de 6,734 ns entre actualización y muestreo.

Las seis pruebas de `make verify-timing` pasaron. La nueva prueba recorre
un cuadro completo: 1.237.500 posiciones, 921.600 píxeles visibles, pulsos
horizontales de 40 píxeles y un pulso vertical de cinco líneas. Comprueba
colores en límites de celda, borrado, sincronismos, fase de muestreo y reinicio.
No se repitieron las 250 ejecuciones de cocotb del cambio anterior; esas
ejecuciones pertenecen a la evidencia de ADR 058. La integración de los
dos módulos superiores se verificó mediante compilación completa en Quartus.

Los valores siguientes son los mínimos entre los modelos lento y rápido,
a 0 y 85 grados Celsius y 1100 mV; corresponden a una implementación por
arquitectura, no a cinco réplicas experimentales.

| Comprobación | Monociclo, ns | Segmentada, ns |
|---|---:|---:|
| Establecimiento global | 1,704 | 2,424 |
| Retención global | 0,161 | 0,161 |
| Establecimiento de las 25 salidas al DAC | 2,411 | 2,424 |
| Retención de las 25 salidas al DAC | 4,857 | 4,843 |
| Límite máximo de latencia H/V | 3,718 | 2,966 |
| Límite mínimo de latencia H/V | 4,004 | 4,139 |
| Bus de inspección, límite de 10 ns | 4,294 | 3,789 |
| Ancho mínimo de pulso del modelo FPGA | 0,612 | 0,612 |

Cada esquina informa 25 rutas de establecimiento y 25 de retención al DAC,
y dos rutas de cada tipo para H/V. No hay asignaciones SDC ignoradas,
relojes ilegales ni entradas, salidas o relojes sin restricciones. Las
excepciones de reinicio y sincronizadores continúan delimitadas como en
ADR 058; las salidas VGA no se excluyen del análisis. Recuperación y remoción
no presentan rutas activas con esas excepciones y no aportan una holgura medida.

Los informes completos por esquina, registros de simulación, resúmenes de
ajuste, bitstreams candidatos, restricciones y hashes se conservan en
`build/vga_output_timing_2026-11-13/`. `manifest.json` identifica las fuentes
corregidas y la evidencia. Se preservan los bitstreams originales de campaña.

## Alcance pendiente de validación física

El resultado temporal depende del presupuesto de ±0,5 ns y del modelo de E/S
de Quartus para Cyclone V y 3.3-V LVTTL. Deben confirmarse las cargas externas
y los retardos de placa. También quedan pendientes la programación de estos
candidatos y la observación del vídeo en la FPGA DE1-SoC; no se ha medido
el reloj ni la integridad de señal en los pines del DAC.

La tabla 6 del DAC exige pulsos altos y bajos de al menos 2,85 ns para el
grado de 140 MHz. La forma de onda nominal satisface esa duración, pero el
informe de ancho de pulso de Quartus recoge los requisitos del dispositivo
FPGA; no sustituye su comprobación física en el ADV7123. Debe confirmarse
el grado del componente instalado para la frecuencia utilizada.

Las réplicas y mediciones históricas de la tesis conservan su alcance original.
Este ajuste posterior no las valida retroactivamente ni actualiza sus cifras
de frecuencia máxima, recursos o rendimiento.
