# Preparación de CoreMark antes de medir

Las variantes de campaña son `coremark_iter1` y `coremark_iter10`, ambas con
`RUN_MODE=PERFORMANCE_RUN` y `TOTAL_DATA_SIZE=2000`. El script
`measure_benchmarks.py` las compila de forma incremental antes de iniciar las
simulaciones seleccionadas. La etapa `preflight` hace la misma preparación,
para detectar un problema antes de las síntesis y las suites largas.

La existencia de `build/coremark_iter*/coremark.elf` no acredita que el programa
corresponda al puerto actual. Antes de simular se comprueba:

- El símbolo `coremark_validation` y su registro de 64 bytes.
- `tohost=0x6000`.
- El bloque estático de 2000 bytes.
- Las semillas de rendimiento y el número de iteraciones solicitado.

Estas comprobaciones verifican la configuración del binario. La corrección de
los CRC y la comparación contra el modelo Python se comprueban durante la
ejecución, como antes. El modo `--from-csv` conserva su carácter de lectura
histórica y no recompila programas.

La variante física de 2000 iteraciones se prepara con `make prepare-coremark`
y también desde el preflight y el capturador de FPGA. Usa las mismas
comprobaciones del ELF. La captura del estado CRC físico se describe en
[CoreMark en FPGA](coremark_physical_crc.md).

## Error `missing CRC record`

Los binarios antiguos podían usar `tohost=0x5000` y carecer del registro de CRC.
Su programa llegaba a finalizar, pero el validador devolvía `crc-fail` porque no
podía acreditar su resultado. No era evidencia de un CRC calculado diferente:
faltaba el propio registro de validación.

Con la preparación integrada, una ejecución normal reconstruye esos binarios.
Para repetir solo los casos de CoreMark:

```sh
.venv/bin/python3 scripts/measure_benchmarks.py \
  --only coremark_iter1 coremark_iter10
```

Para comprobar los casos que previenen la regresión:

```sh
.venv/bin/python3 -m unittest verification/test_benchmark_preparation.py
```

## Imágenes y logs de simulación

La validación pasa a Icarus las imágenes generadas para ese ELF y las mismas
profundidades con las que se construyeron. Así, el arranque no usa por accidente
una imagen general de 4096 palabras en una memoria simulada de 16384 palabras.
El conversor se ejecuta con el intérprete Python activo, incluidas las
dependencias del entorno virtual.

Al ejecutar el medidor directamente, la frecuencia se toma primero de
`results/results_fmax.csv`, que resume las réplicas de la campaña. El archivo
histórico `results_synthesis.csv` solo se usa como alternativa si falta el
primero. La campaña también puede pasar explícitamente `--fmax-csv`.

Cada ejecución conserva el log completo junto a sus CSV, XML y evidencia JSON:
`results/benchmark_<programa>_<arquitectura>.log`. Los avisos del simulador deben
interpretarse con el resultado de la prueba: los avisos de soporte parcial de
`unique case` no equivalen al fallo `missing CRC record`.
