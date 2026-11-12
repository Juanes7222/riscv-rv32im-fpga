# Captura física de la validación CRC de CoreMark

El fallo «physical CoreMark CRC evidence missing» no indica un fallo del
programador JTAG. Los contadores congelados acreditan finalización; los
binarios antiguos podían finalizar aunque los CRC fueran incorrectos.

Se encontró que `build/coremark/coremark.elf`, la carga de 2000 iteraciones
usada en la placa, seguía sin `coremark_validation`. El flujo ya preparaba las
variantes de 1 y 10 iteraciones, pero omitía esta variante física. Los datos
anteriores se conservan sin promoverlos a resultados con CRC válido.

## Preparación y ejecución

`make prepare-coremark`, el preflight y el capturador preparan incrementalmente
la carga física: 2000 iteraciones, `PERFORMANCE_RUN`, 2000 bytes de trabajo y
`tohost=0x6000`. Comprueban el registro CRC y las semillas del ELF. Antes de
sustituir un ELF obsoleto, lo guardan en `build/coremark/previous/<sha256>.elf`.
Los smoke tests usan la misma variante, sin crear otra configuración en su
directorio por accidente.

Para retomar la campaña completa:

```sh
make full-campaign
```

La comparación del manifiesto con el ELF reconstruido invalida las réplicas
que contienen el binario antiguo: se archivan y recompilan. Las suites y los
benchmarks cuya procedencia siga coincidiendo se reutilizan. No se modificó
el RTL para esta captura.

Si las réplicas ya corresponden al ELF corregido y solo falta medir CoreMark:

```sh
make measure-hardware ARCH=single_cycle ELF=build/coremark/coremark.elf
make measure-hardware ARCH=pipeline ELF=build/coremark/coremark.elf
make validate-campaign
```

## Lectura en la consola VGA

1. Soltar reset con KEY[0] y esperar a que finalice la ejecución y se congelen
   los contadores.
2. Anotar `CyclesToPass` e `InstrToPass`. Anteponer `0x` a las lecturas en
   hexadecimal, especialmente si solo contienen cifras numéricas.
3. Leer **x5**, también llamado **t0**, en la tabla de registros. No leer
   `Data Write`, que muestra una señal de otra parte del procesador.
4. Introducir el valor observado cuando lo solicite el capturador.

| x5/t0 observado | Interpretación del puerto corregido |
|---|---|
| `00000001` | Las comprobaciones funcionales CRC terminaron correctamente |
| `00000003` | El puerto detectó un fallo de validación |
| Sin lectura | Evidencia pendiente; no se registra un éxito CRC |

`core_validation.c` compara los CRC de listas, matrices y estados con las
tablas conocidas de CoreMark. `main` devuelve 0 solo si ese registro indica
éxito. `start.S` transforma esa devolución en 1 o 3, la conserva en x5/t0 y la
escribe en `tohost`. El bucle final no cambia x5. El estado se lee después de
que los contadores confirmen el final del programa. Un 1 de un binario antiguo
sin este contrato no acredita CRC y se rechaza.

Este método captura **el resultado de las comprobaciones CRC**, mediante el
estado de salida físico. No captura las palabras CRC individuales ni valida
el temporizador interno de CoreMark. Las tasas siguen derivándose de ciclos
y reloj; esta evidencia no declara certificación oficial del benchmark.

## Evidencia y reportes

Antes de programar se ejecuta `check_mem_init.py`, que compara las imágenes de
memoria compiladas disponibles con las fuentes. Se exige la coincidencia de
IMEM; si Quartus implementa DMEM en lógica sin exportar su imagen, esa
limitación permanece en el log y no se declara una lectura de DMEM. La
captura registra:

- Ciclos, instrucciones, arquitectura, reloj, dirección de `tohost` y x5/t0.
- Hashes del RTL, ELF y bitstream, y el protocolo de retiro.
- ELF y bitstream archivados, y log de comprobación de imágenes.
- Una observación JSON identificada por su hash en `results/hardware_evidence/`.

Los CSV `_v2` amplían su esquema conservando las filas anteriores. La fila más
reciente de cada arquitectura sustituye la fila histórica solo en el informe
derivado. El CSV histórico original permanece intacto.

El generador vuelve a comprobar los hashes, la configuración del ELF, el
estado observado, los contadores y la correspondencia con las réplicas. Los
archivos de evidencia forman parte de las entradas del manifiesto del
informe. Una observación de otra ejecución o un indicador booleano aislado
no elimina el pendiente de validación.
