# Comprobación de la interfaz VGA

Este procedimiento respalda los objetivos de visualización y comparación
experimental. No añade una caracterización eléctrica de la FPGA DE1-SoC
ni una evaluación educativa. La política está en
[ADR 060](../decisions/060_vga_sensitivity_gate.md).

## Ejecución

Desde WSL, con el entorno y Quartus configurados como en el proyecto:

```bash
make full-campaign
```

La campaña ejecuta las pruebas de la automatización y los seis bancos de
visualización, reinicio y transferencia. Cada `make replica` ejecuta el
análisis VGA después del ajuste y antes de sellar el manifiesto de la réplica.
Una réplica previa sin esa evidencia no se reutiliza automáticamente.
La validación estricta del informe también utiliza esta comprobación de
integridad de réplicas. La etapa física sigue solicitando las lecturas
observadas en el monitor; no mide retardos de pista.

Para examinar un proyecto ya ajustado y vigente:

```bash
make vga-timing ARCH=single_cycle VGA_TIMING_DIR=build/vga_timing/sc_run1
make vga-timing ARCH=pipeline VGA_TIMING_DIR=build/vga_timing/pipe_run1
```

El destino debe ser nuevo o estar vacío. Si faltan los archivos de ajuste,
o son anteriores a las fuentes y entradas, hay que compilar primero. El
análisis no programa la FPGA ni cambia el RTL, el SDC nominal o el bitstream.
Los scripts no exportan las cargas temporales a los proyectos.

## Lectura de los informes

- `sensitivity.csv`: 120 casos; cada uno contiene los mínimos entre las 25
  rutas al DAC para establecimiento y retención. Las columnas identifican
  carga, presupuesto de desfase, modelo y temperatura.
- `baseline.csv`: comprobaciones globales del proyecto nominal. Un análisis
  de recuperación/remoción sin rutas no equivale a un margen positivo.
- `summary.csv` y `summary.json`: mínimos por escenario con ±0,5 ns, mayor
  presupuesto ensayado que pasa y umbral lineal aproximado de margen cero.
  Ese umbral es una estimación del modelo fijo, no un retardo medido de placa.
- `board_model.txt`: parámetros explícitos del proyecto; la ausencia de una
  asignación significa que se usan valores predeterminados del modelo.
- Informes por caso, `analysis.log`, copia de las fuentes del análisis y SDC,
  y `manifest.json`: trazabilidad y verificación de integridad.

Los escenarios capacitivos son hipótesis de 10/20 pF, no límites garantizados
por el fabricante. El presupuesto nominal de ±0,5 ns también es una hipótesis.
La sensibilidad conserva los demás parámetros del modelo de placa del
proyecto y no representa una extracción distribuida completa de pistas.
No debe elegirse un escenario favorable para ocultar violaciones en otro.

## Observación física complementaria

1. Registrar revisión, hash del SOF, arquitectura, programa, reloj configurado
   y monitor. Confirmar la revisión de la placa y el grado del DAC instalado.
2. Comprobar texto, bordes de la región visible, colores y estabilidad del
   sincronismo. Probar reinicio, pausa y avance por ciclos; anotar anomalías.
3. Esperar a que la consola presente el estado final estable antes de leer
   `CyclesToPass`, `InstrToPass` y el estado funcional. Conservar capturas
   identificadas para ambas arquitecturas.
4. Informar estas comprobaciones como validación funcional observada. No
   permiten afirmar tiempos eléctricos medidos en las entradas del DAC.

Una captura instrumental o un modelo de pistas permitiría ampliar esa
evidencia. Sin ellos, el resultado sigue siendo un análisis temporal
condicionado y una observación funcional en las condiciones ensayadas.
Los requisitos del DAC se toman de su hoja de datos, no se atribuyen al
procedimiento experimental ni se presenta ±0,5 ns como dato de Terasic.
