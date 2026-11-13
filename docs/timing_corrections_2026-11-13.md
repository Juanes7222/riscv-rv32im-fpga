# Correcciones de reinicio y transferencia a la consola

Se corrigieron el uso del reinicio externo en la lógica del procesador y la
captura directa de señales del procesador desde el reloj de vídeo. La decisión
y el contrato temporal se describen en [ADR 058](decisions/058_reset_release_and_console_cdc.md).

## Cambios aplicados

- Liberación del reinicio sincronizada en cada dominio; bloqueo hasta el enganche
  del PLL correspondiente y estado inicial de reinicio al configurar la FPGA.
- Transferencia del bus completo de inspección mediante petición y confirmación.
  Los contadores de 64 bits, registros y señales de instrucción se capturan
  juntos en el dominio de origen y permanecen estables durante la transferencia.
- Corrección del detector de pulsación del cargador y de la captura del selector.
- SDC idénticos con entrada física de 50 MHz, relojes derivados e incertidumbre
  recomendada por el modelo. Se sustituyeron las exclusiones globales CPU–vídeo
  por restricciones específicas de los sincronizadores y del bus retenido.

## Evidencia obtenida

Las 250 ejecuciones existentes de cocotb terminaron sin fallos inesperados:
111 comunes, 51 específicas de monociclo y 88 de la arquitectura segmentada.
Esta cifra conserva las limitaciones conocidas de modo máquina y no representa
conformidad exhaustiva con RISC-V. Las cinco comprobaciones adicionales de
reinicio, transferencia y visualización también terminaron satisfactoriamente.

Se generó una implementación nueva por arquitectura, con semilla 5, y se examinó
con Quartus Prime 25.1std.0. Los valores siguientes son los mínimos de cada tipo
entre los modelos lento y rápido, a 0 y 85 grados Celsius y 1100 mV. Son holguras
de las rutas incluidas en el análisis; no son promedios de cinco réplicas.

| Comprobación | Monociclo, ns | Segmentada, ns |
|---|---:|---:|
| Establecimiento global de rutas restringidas | 1,895 | 2,807 |
| Retención global de rutas restringidas | 0,166 | 0,158 |
| Transferencia del bus de inspección, límite de 10 ns | 4,044 | 4,113 |
| Ancho mínimo de pulso | 0,612 | 0,612 |

El informe de recuperación y remoción no encontró rutas activas con las
exclusiones de los límites de reinicio. Ese resultado no es una holgura positiva
ni sustituye la revisión estructural de esos sincronizadores.

Ambos diseños tienen cero entradas y cero relojes sin restricciones. Permanecen
28 salidas VGA sin presupuesto temporal externo. Se conserva este pendiente;
no se asignaron retardos arbitrarios para obtener un resumen sin advertencias.
Por tanto, todavía no se declara cierre temporal integral de la interfaz VGA.

## Reproducción

Para las pruebas de reinicio y consola, con Icarus Verilog disponible:

```sh
make verify-timing
```

Las suites funcionales se ejecutan con `make verify-full` en el entorno de cocotb
del proyecto. Para una nueva compilación, ejecutar primero `make sync-all`, pues
hay dos módulos compartidos nuevos. El informe detallado de una implementación
ya ajustada se obtiene con rutas absolutas:

```text
quartus_sta -t synthesis/report_physical_timing.tcl <directorio-del-proyecto> <directorio-de-informes>
```

Los informes de esta revisión se conservan en
`build/timing_corrections_2026-11-13/`, con los registros de verificación, las
huellas de las fuentes, los informes de las cuatro condiciones y los candidatos
de programación. Las bases de síntesis usadas para comprobarlos pertenecen a
una copia de trabajo aislada; la campaña original y sus archivos `.sof` se
conservaron. Las rutas internas de los informes identifican esa copia.

## Alcance respecto a la tesis

La campaña publicada utiliza las entradas congeladas anteriores a estas
correcciones. Las nuevas implementaciones necesitan validación física y una
campaña propia antes de sustituir los resultados de frecuencia, recursos o
desempeño. Esta revisión no atribuye al cruce de reloj la causa de una lectura
física previa que se corrigió manualmente: ese origen no fue demostrado.

Para la consola, una captura de grupo coherente no implica una captura simultánea
de toda la pantalla o de las memorias espejo mientras el procesador escribe.
La inspección detenida permite esperar la actualización estable de la vista.

## Referencias técnicas

- [Intel: consideraciones de cruces de reloj](https://www.intel.com/content/www/us/en/content-details/652881/clock-domain-crossing-considerations.html).
- [Intel: reglas de restricciones para cruces de reloj](https://www.intel.com/content/www/us/en/docs/programmable/683353/23-4/clock-domain-crossing-constraint-guidelines).
- [Intel: mecanismos de transferencia y confirmación](https://cdrdv2-public.intel.com/654507/an545.pdf).

La sintaxis Tcl se contrastó además con la ayuda de la instalación de Quartus
25.1std.0 utilizada para ejecutar los informes.
