# Recomendaciones de revisión del proyecto de grado RISC-V

**Documento de trabajo basado en la reunión de revisión con los profesores.**  
**Objeto:** organizar, explicar y convertir en acciones las observaciones realizadas al documento de grado sobre el diseño, implementación, verificación y comparación de un procesador RISC-V monociclo y uno segmentado en FPGA.

> **Alcance de estas notas.** Este documento organiza las recomendaciones presentes en la transcripción de la reunión; no es una revisión del manuscrito completo ni una validación independiente de las especificaciones de la tarjeta, los benchmarks o las soluciones de hardware. Se diferencia entre recomendaciones expresas de los profesores, explicaciones de su fundamento y acciones sugeridas para aplicarlas. Las cuestiones técnicas pendientes se marcan como **por verificar**.

## 1. Idea central de la reunión

La principal recomendación no consiste en añadir texto indiscriminadamente ni en mejorar solo la ortografía. Los profesores piden que el documento tenga una argumentación técnica clara, que cada referencia bibliográfica cumpla una función, que las métricas respondan a los objetivos y que las afirmaciones estén sustentadas por las implementaciones y pruebas efectivamente realizadas.

El trabajo compara dos microarquitecturas de un mismo procesador. Para que la comparación tenga valor académico, es necesario distinguir las características inherentes a cada microarquitectura de los resultados condicionados por la tecnología FPGA y por el entorno de implementación. Asimismo, el texto debe permitir identificar sin ambigüedad qué hicieron los autores citados, qué se hizo en el proyecto y qué queda pendiente.

Los profesores también definieron una secuencia de revisión: preparar una versión inicial coherente, enviarla a Carlos para una primera lectura, incorporar sus observaciones y posteriormente realizar otra revisión conjunta.

## 2. Redacción académica y terminología técnica

### 2.1. Traducir términos cuando exista un equivalente claro en español

El profesor recomendó reducir el uso innecesario de anglicismos, en particular en los objetivos y en las explicaciones generales. El uso de inglés puede ser razonable al introducir una denominación estándar, pero se debe establecer una terminología consistente y mantenerla a lo largo del documento.

| Expresión encontrada | Alternativa recomendada | Criterio de aplicación |
|---|---|---|
| `hazard` | riesgo o dependencia de datos/control, según el fenómeno | Definir el término de manera técnica en su primera aparición. Evitar traducirlo mecánicamente cuando se refiere a un tipo específico de conflicto. |
| `testbench` / `testbenches` | banco de pruebas / bancos de pruebas | Preferir el equivalente español en el texto académico. |
| `pipeline` | segmentación, procesador segmentado o *pipeline* | Puede conservarse *pipeline* al definir el concepto, pero mantener luego una denominación homogénea. |
| `CPI` | ciclos por instrucción (CPI) | En los objetivos y en la primera aparición desarrollar el acrónimo. |
| `throughput` | tasa de procesamiento o rendimiento en instrucciones por unidad de tiempo | El profesor propuso «desempeño»; conviene precisar la magnitud cuando se trate de una métrica cuantitativa. |
| `write-back` | etapa de escritura de resultados | Presentar ambos términos al introducir las etapas del procesador, si resulta útil. |
| `benchmark` | prueba de rendimiento o banco de evaluación | Conservar el nombre propio de la prueba, como CoreMark. |

**Por qué importa.** Los objetivos y el resumen deben poder ser comprendidos sin que el lector tenga que interpretar una sucesión de siglas y términos ingleses. Además, una traducción bien seleccionada permite separar conceptos que a veces se confunden: el **CPI** mide ciclos por instrucción, la **frecuencia** se mide en ciclos por segundo y la **tasa de procesamiento** puede expresarse en instrucciones por segundo. «Desempeño» es un concepto más amplio y no siempre constituye una traducción matemática exacta de *throughput*.

**Acción:** revisar los objetivos, el resumen, el marco teórico, la metodología y las conclusiones para unificar los términos. Construir un glosario si el texto contiene numerosas señales, etapas y mecanismos de la arquitectura.

### 2.2. Definir los conceptos en su primera aparición

Al inicio de la transcripción se sugirió definir *hazard*. Es una recomendación extensible a los conceptos que sostienen el análisis: riesgos de datos, riesgos de control, derivación de datos (*forwarding*), paradas (*stalls*), vaciado de registros de segmentación (*flush*), memoria síncrona, CPI y camino crítico.

No basta con traducir una expresión: hay que indicar a qué fenómeno se refiere dentro de la microarquitectura estudiada. Por ejemplo, un riesgo de datos aparece cuando una instrucción depende de un resultado que todavía no está disponible en la etapa en la que se necesita. El mecanismo de derivación puede resolver algunos casos, mientras que otros requieren introducir una parada.

**Acción:** identificar dónde aparece por primera vez cada término y añadir una definición breve, directamente relacionada con el diseño implementado. Confirmar con Carlos las elecciones terminológicas que afecten la precisión conceptual.

### 2.3. Desarrollar las siglas en los objetivos

El profesor mencionó explícitamente que preferiría no usar «CPI efectivo» sin explicación en un objetivo. La forma recomendada es **«ciclos por instrucción (CPI)»**; después puede emplearse la sigla.

Una formulación orientativa, pendiente de contrastar con el objetivo original y con las métricas realmente calculadas, sería:

> Comparar experimentalmente las microarquitecturas monociclo y segmentada mediante la medición de su frecuencia máxima de operación, el promedio de ciclos por instrucción (CPI), la tasa de procesamiento de instrucciones y la utilización de recursos de hardware, bajo condiciones de implementación equivalentes.

Esta redacción es solo un ejemplo. Si una métrica no se mide o no tiene un procedimiento reproducible, debe eliminarse o definirse adecuadamente antes de mantenerla en el objetivo.

## 3. Calidad argumentativa: justificar cada párrafo

### 3.1. Pregunta de control para la revisión

Una de las recomendaciones más importantes del profesor fue leer el documento **párrafo por párrafo** y responder:

> ¿Para qué sirve este párrafo? ¿Qué afirmación quiero sostener, qué idea quiero desarrollar o qué planteamiento quiero cuestionar con él?

Esto exige evaluar la función de cada párrafo en la estructura del capítulo. Un párrafo puede introducir un concepto necesario, presentar evidencia previa, explicar una decisión de diseño, delimitar un alcance, describir un resultado o interpretar una limitación. Si no se puede identificar esa función, es probable que el texto deba reescribirse, integrarse con otro o eliminarse.

**Ejemplo.** No aporta suficiente valor describir que un procesador ajeno usa Verilog y presenta determinadas métricas si después no se explica cómo ese antecedente ayuda a justificar las decisiones del proyecto, su método de verificación o la interpretación de sus resultados.

### 3.2. Evitar referencias ambiguas entre párrafos

Durante la reunión se discutió la expresión «este estudio», porque no resultaba claro si se refería al antecedente bibliográfico o al proyecto de grado. El problema no era solo usar un punto aparte: era la ambigüedad del sujeto y la relevancia del argumento.

**Redacción ambigua:** «Este estudio ofrece un punto de referencia cuantitativo…».

**Redacción más precisa si se describe un antecedente:** «El trabajo de [Autores, año] presenta resultados de frecuencia máxima y utilización lógica para la arquitectura que implementa…».

**Redacción más precisa si se describe el proyecto propio:** «En el presente proyecto se comparan ambas microarquitecturas utilizando…».

**Acción:** revisar expresiones como «este estudio», «esta implementación», «dicho procesador», «estos resultados» y «la propuesta», especialmente en los antecedentes. Cada una debe tener un referente inequívoco.

### 3.3. Usar la IA como apoyo de revisión, no como sustituto de lectura

El profesor permitió y recomendó utilizar una herramienta de IA para localizar problemas de ortografía, redacción y coherencia. Sin embargo, insistió en que el estudiante debe **leer, comprender y evaluar personalmente** el texto final.

El riesgo señalado durante la reunión es incorporar afirmaciones que parecen académicas pero no se corresponden con el alcance real del proyecto. Por ejemplo, mencionar eficiencia energética sin medirla, o describir como relevante un antecedente cuya implementación de la ISA es mucho más limitada, puede crear expectativas metodológicas que no se cumplen.

**Procedimiento sugerido:** realizar una primera revisión manual, obtener observaciones de una IA sobre problemas localizados, decidir qué correcciones son válidas, verificar las afirmaciones técnicas y leer finalmente el documento de principio a fin para comprobar la continuidad del argumento.

## 4. Citas, referencias bibliográficas y antecedentes

### 4.1. Referenciar la suite de pruebas RISC-V

Al leer el objetivo de verificar funcionalmente ambas implementaciones mediante la suite RISC-V, el profesor preguntó de dónde procedía. Tras conocer que se trataba de una suite alojada en GitHub, sugirió **añadir una referencia bibliográfica en la primera mención relevante**.

La lista de referencias al final del documento, por sí sola, no indica qué afirmación respalda cada fuente. Por ello, se debe citar la suite en el lugar donde se explique su procedencia o su utilización, sin introducir referencias innecesarias en todos los objetivos.

**Acción:** identificar el repositorio y la versión o revisión exacta utilizados, verificar su denominación y añadir la referencia en la metodología o sección de verificación donde se describe la suite. Comprobar la coherencia con la bibliografía y, si se cita desde los objetivos, seguir el criterio de los asesores y el formato institucional.

### 4.2. Conservar únicamente antecedentes que aporten a la comparación

El profesor cuestionó un antecedente que implementaba **23 instrucciones** cuando el proyecto propio incluía un alcance de ISA más amplio, relacionado con RV32I y la extensión M. La crítica no implica que sea imposible citar arquitecturas más pequeñas: significa que debe existir una razón académica clara para hacerlo.

Según la reunión, si no hay una razón específica para mantener esa referencia, corresponde retirarla. Un antecedente puede justificar su inclusión si permite comparar soluciones a un problema similar, métodos de verificación, decisiones de implementación o resultados bajo condiciones suficientemente explicadas. No debe conservarse simplemente porque apareció durante la búsqueda bibliográfica.

**Acción:** revisar el antecedente atribuido en la conversación a Egozi y otros; leer la publicación original, comprobar las instrucciones implementadas y decidir si tiene valor específico. Si se elimina, retirar también los párrafos que dependan exclusivamente de él y revisar las transiciones del capítulo.

### 4.3. Se pueden citar implementaciones RV32I sin extensión M

El profesor aclaró que **no es obligatorio que todos los antecedentes implementen RV32IM**. Una implementación RV32I puede ser relevante, especialmente si cubre adecuadamente el conjunto base y sus resultados sirven para explicar una diferencia arquitectónica o metodológica.

La recomendación fue preferir implementaciones completas o suficientemente representativas de la arquitectura que se dice implementar. No se debe aplicar un filtro mecánico basado únicamente en el número de instrucciones: hay que comprobar la versión de la especificación, las instrucciones exigidas, las opcionales y el tratamiento de las instrucciones de sistema antes de afirmar que un núcleo es «completo».

**Acción:** clasificar los antecedentes según ISA soportada, microarquitectura, plataforma FPGA, memoria, verificación, métricas y utilidad concreta para el proyecto.

### 4.4. No prometer mediciones que el proyecto no realiza

El profesor observó referencias a eficiencia energética, potencia y consumo. El estudiante aclaró que **no planeaba realizar una medición de consumo**. En consecuencia, esos conceptos no deberían presentarse como métricas del proyecto ni como resultados esperados.

Aunque Quartus puede ofrecer funcionalidades de estimación de potencia, **la posibilidad de producir una estimación no equivale a haber definido una metodología de evaluación energética**. Harían falta entradas, condiciones de actividad y criterios de comparación apropiados.

**Acción:** buscar en objetivos, justificación, antecedentes, metodología, resultados y conclusiones expresiones como «potencia», «consumo», «eficiencia energética» y «eficiencia»; corregirlas según el contexto. Se pueden mencionar métricas energéticas utilizadas por terceros si se explica su pertinencia, sin atribuirlas al proyecto propio ni insinuar una comparación que no se hará.

### 4.5. Limitar las afirmaciones a la plataforma realmente utilizada

El profesor cuestionó una afirmación demasiado amplia sobre «plataformas Intel FPGA». El estudio se realiza sobre una tarjeta concreta y no autoriza generalizaciones a todas las familias FPGA del fabricante.

La redacción debe identificar con exactitud **el modelo de la tarjeta, el dispositivo FPGA y las condiciones de compilación**. Se pueden extraer reflexiones conceptuales más generales acerca de las microarquitecturas, pero los valores medidos corresponden a una implementación y una tecnología específicas.

**Acción:** reemplazar formulaciones genéricas del tipo «en plataformas Intel FPGA» cuando se estén describiendo resultados experimentales concretos. En la transcripción aparece «DE10-Lite», mientras que otras partes de la conversación aluden a una tarjeta con características diferentes; se debe verificar qué modelo figura en el manuscrito final. No asumir que DE10-Lite y DE1-SoC son equivalentes.

## 5. Metodología comparativa y selección de métricas

### 5.1. Diferenciar propiedades arquitectónicas de resultados tecnológicos

El profesor dedicó una explicación extensa a este punto. La frecuencia máxima de una implementación depende del circuito y de la tecnología FPGA: recursos físicos, retardos, herramientas, restricciones temporales y decisiones de síntesis y ubicación. En cambio, medidas como el CPI describen aspectos de la ejecución que pueden analizarse a nivel microarquitectónico, aunque su valor también depende de la mezcla de instrucciones, de las dependencias, de los accesos a memoria y de las condiciones de prueba.

La intención académica es que las conclusiones no pierdan todo su sentido si alguien reproduce el diseño en una FPGA distinta. Esto exige evitar la confusión entre una **observación dependiente de la plataforma** y una **característica general del diseño**.

| Medida o aspecto | Qué indica | Qué debe documentarse |
|---|---|---|
| Frecuencia máxima de operación (Fmax) | Límite temporal de la implementación bajo restricciones determinadas | FPGA, herramientas, restricciones, análisis temporal y configuración del diseño |
| CPI promedio o efectivo | Ciclos empleados por instrucción, para una ejecución definida | Método de conteo, instrucciones consideradas, programa, riesgos y paradas |
| Tasa de procesamiento | Instrucciones completadas por unidad de tiempo | Frecuencia usada, CPI, definición de instrucción completada y carga de prueba |
| Recursos utilizados | Costo de implementación en elementos lógicos, registros, memoria, DSP, etc. | Dispositivo, configuración y categorías de recursos informadas por la herramienta |
| Camino crítico | Ruta temporizada que limita el período mínimo del reloj | Origen, destino, lógica de la ruta y restricciones de temporización |
| Consumo de potencia | Potencia o energía bajo condiciones específicas | **No está incluido como medida comprometida en la reunión**; solo agregar si se define y ejecuta una metodología válida |

### 5.2. El CPI es central, pero no debe analizarse de forma aislada

El profesor recomendó dar un peso especial al **número de ciclos por instrucción**, porque ayuda a explicar las diferencias microarquitectónicas sin reducir todo el análisis al reloj obtenido en una FPGA particular.

Para una ejecución con un conjunto definido de instrucciones retiradas o completadas, una expresión habitual es:

\[
\mathrm{CPI}_{\mathrm{prom}} = \frac{N_{\mathrm{ciclos}}}{N_{\mathrm{instrucciones}}}
\]

Si las definiciones y condiciones son consistentes, una tasa media aproximada de instrucciones completadas por segundo se expresa como:

\[
R_{\mathrm{inst}} = \frac{f_{\mathrm{reloj}}}{\mathrm{CPI}_{\mathrm{prom}}}
\]

De aquí se desprende que una arquitectura con mayor frecuencia no necesariamente tiene mejor tasa de procesamiento si requiere muchos más ciclos por instrucción. A la inversa, un menor CPI no garantiza mejor rendimiento temporal si la frecuencia cae de manera significativa.

**Acción:** incluir una explicación explícita de qué mide cada variable, cómo se obtiene y por qué es pertinente para la comparación. Si el monociclo pretende CPI = 1, comprobar que esto se cumpla bajo el modelo de memoria y la definición experimental adoptados, en lugar de asumirlo por el nombre de la arquitectura.

### 5.3. Comparar en condiciones equivalentes

En el texto comentado durante la reunión se mencionó el uso de la misma suite de pruebas y de restricciones de síntesis equivalentes. El criterio de comparabilidad debe preservarse, pero no basta con afirmarlo: conviene detallar qué parámetros son comunes y cuáles son diferentes por necesidad arquitectónica.

Por ejemplo, son factores relevantes la placa utilizada, la versión de Quartus, las restricciones temporales, la implementación de las memorias, el programa ejecutado, la forma de contar ciclos e instrucciones y la configuración de extensiones de la ISA.

**Acción:** elaborar una tabla metodológica que distinga condiciones compartidas, diferencias inevitables entre arquitecturas y posibles amenazas a la validez de los resultados.

### 5.4. No sobreinterpretar las frecuencias máximas

En la conversación se mencionaron, de manera ilustrativa, resultados cercanos a 30 MHz para una versión del proyecto y a 50,2 MHz para otro ejemplo mostrado por el profesor. **No constituyen por sí solos una comparación válida** porque no se confirmó que correspondieran al mismo diseño, restricciones, FPGA y configuración.

La frecuencia debe presentarse como una medición experimental reproducible, no como una clasificación absoluta de calidad entre diseños o proyectos externos.

## 6. Camino crítico del procesador monociclo

### 6.1. Explicación ofrecida durante la reunión

El profesor utilizó un diagrama temporal de una instrucción de carga (`LW`) para explicar por qué el procesador monociclo está limitado por la suma de los retardos que atraviesa una operación compleja. En el ejemplo se distinguieron la obtención de la instrucción, el banco de registros y la ALU, el acceso a memoria de datos y la escritura del resultado (*write-back*).

El principio relevante es que **el período del reloj debe ser suficiente para que los datos recorran la ruta combinacional más lenta entre los elementos secuenciales correspondientes, con los márgenes temporales exigidos**. Al reducir el retardo de esa ruta, puede aumentar la frecuencia máxima admitida.

Esta explicación es conceptual: el camino crítico real debe obtenerse del análisis temporal de la implementación. No corresponde afirmar, sin evidencia, que `LW` es siempre la instrucción o ruta más lenta. También puede haber rutas relacionadas con otras unidades, por ejemplo la multiplicación o división, dependiendo de cómo se hayan diseñado.

### 6.2. Cómo trasladarlo al documento

El capítulo de arquitectura o resultados debería explicar: cuáles son las etapas lógicas recorridas por las instrucciones más exigentes, qué ruta identificó la herramienta como crítica, cómo se relaciona su retardo con la Fmax y qué cambios de diseño alteraron esa ruta.

**Acción:** utilizar los reportes de temporización de Quartus para identificar los caminos reales y acompañar los diagramas con una interpretación que distinga la explicación didáctica del resultado experimental.

## 7. Problema de la memoria síncrona en FPGA

### 7.1. Dificultad descrita por el estudiante

En la reunión se explicó que la implementación monociclo había encontrado una limitación al trabajar con memorias de bloques síncronas. Si la instrucción solicitada solo aparece después de un flanco de reloj y la arquitectura no anticipa correctamente la dirección, la ejecución puede exigir un ciclo adicional, contradiciendo el comportamiento de CPI = 1 buscado en el diseño.

Para evitar esa latencia, el estudiante había implementado una memoria mediante recursos lógicos de la FPGA en lugar de utilizar los bloques internos de memoria. Esa elección afecta al consumo de recursos, la escalabilidad, los tiempos de compilación y la capacidad disponible para almacenar programas de prueba grandes.

### 7.2. Alternativas mencionadas

**Alternativa A: introducir una máquina de estados.** El profesor explicó que podría separarse la lectura de instrucciones de otras operaciones mediante estados, pero esto elevaría el número de ciclos por instrucción y cambiaría el tipo de implementación respecto al monociclo pretendido. Es una solución posible a la latencia, pero no conserva automáticamente el criterio de CPI = 1.

**Alternativa B: anticipar la dirección de la memoria de instrucciones.** El profesor sugirió suministrar a la memoria síncrona una dirección asociada al **siguiente PC**, en lugar de utilizar exclusivamente el PC actual, con la intención de disponer de la instrucción adecuada en el momento de su ejecución y poder usar Block RAM.

Esta segunda alternativa fue una **propuesta de diseño, no una solución validada en la reunión**. Requiere resolver cuidadosamente la relación entre flancos de reloj, dirección solicitada, salida registrada de memoria y PC arquitectónico. También exige verificar qué sucede con saltos, ramificaciones, redirecciones de flujo, reinicio y cualquier condición que haga que el siguiente PC no sea simplemente `PC + 4`.

### 7.3. Verificaciones obligatorias antes de adoptarla

1. Confirmar el modelo exacto de FPGA y la latencia de lectura de la memoria inferida o instanciada.
2. Dibujar un cronograma ciclo a ciclo con PC, siguiente PC, dirección de memoria e instrucción disponible.
3. Comprobar que la instrucción leída corresponde a la dirección arquitectónica correcta después de saltos y ramificaciones.
4. Determinar si existe algún ciclo extra de llenado, recuperación, parada o burbuja, y cómo afecta el CPI medido.
5. Verificar en Quartus que la memoria se haya implementado efectivamente con bloques de memoria y no con lógica distribuida.
6. Ejecutar pruebas funcionales representativas, incluyendo secuencias de control de flujo, y repetir el análisis temporal.
7. Documentar cualquier cambio en latencia, recursos y frecuencia que impida una comparación directa con la versión previa.

### 7.4. No asumir la capacidad de memoria mencionada verbalmente

El profesor mencionó una capacidad de «64 megas» en relación con la tarjeta. En la transcripción no quedó claro a qué memoria se refería exactamente. **No debe interpretarse sin comprobación como 64 MB de Block RAM interna.** La memoria embebida en el FPGA y la memoria externa disponible en una placa son recursos diferentes, con interfaces, latencias y restricciones distintas.

**Acción:** consultar la documentación oficial del modelo real de FPGA y de la placa; registrar la capacidad de memoria interna en bits y la de memorias externas, si existen; determinar qué memoria puede utilizar efectivamente el núcleo y cuánto espacio necesitan los ejecutables.

## 8. Benchmarks y capacidad de los programas

### 8.1. Dificultad mencionada con CoreMark

El estudiante explicó que algunos programas o configuraciones de prueba excedían la capacidad de la memoria implementada con recursos lógicos. El profesor conectó este problema con la posibilidad de utilizar memorias de bloques.

Esta observación afecta tanto al diseño hardware como a la metodología: no es adecuado prometer pruebas de rendimiento si no se ha demostrado que pueden cargarse y ejecutarse en el sistema que se evaluará.

### 8.2. Decisiones pendientes

**Acción:** identificar los benchmarks citados en el manuscrito, verificar los requisitos reales de cada uno, medir su ocupación de instrucciones, datos, pila y otras regiones, y compararla con el mapa de memoria implementado.

También se debe especificar cómo se compilan los programas, con qué opciones de ISA y ABI, cómo se cargan, cómo se determina que finalizaron correctamente y qué métricas se extraen. Si no es viable ejecutar una prueba estandarizada completa, documentar la limitación y no presentarla como resultado obtenido.

Se discutió expresamente CoreMark; la transcripción menciona también otra prueba sin identificarla de forma inequívoca. Por tanto, no se debe atribuir un nombre adicional sin consultar el manuscrito original.

## 9. Visualización didáctica del pipeline

El profesor valoró positivamente el objetivo de construir un módulo de visualización de estados internos del procesador segmentado. El estudiante indicó que ya había una implementación funcional, pero que no disponía en ese momento de una forma práctica de mostrarla remotamente.

Se habló de conversores de video y de una capturadora USB. La cuestión principal es demostrar la herramienta durante una revisión o sustentación, no adquirir necesariamente un accesorio concreto. La compatibilidad depende de los conectores y del formato de señal de salida.

**Acción:** preparar una demostración reproducible que permita visualizar cómo avanzan las instrucciones y cómo reaccionan las etapas a dependencias, paradas y cambios de flujo. Verificar anticipadamente el camino de captura VGA y conservar evidencia de funcionamiento, como imágenes o grabaciones si las normas del proyecto lo permiten.

También es necesario confirmar el nombre de la placa utilizado en objetivos, metodología, diagramas y conclusiones, dado que la transcripción menciona una DE10-Lite.

## 10. Delimitación del trabajo y de sus afirmaciones

A partir de los comentarios sobre antecedentes, métricas y plataforma se deriva una regla editorial común: **el documento debe diferenciar lo implementado, lo medido, lo tomado de la literatura y lo propuesto para trabajos futuros**.

Esto evita varios problemas: atribuir al proyecto métricas de otros autores, sugerir que se midió potencia sin haberlo hecho, presentar un antecedente como comparable sin explicar sus diferencias, y generalizar resultados de una placa concreta a familias enteras de FPGA.

**Acción:** revisar todas las afirmaciones que contengan verbos como «demuestra», «garantiza», «mejora», «permite», «supera», «es más eficiente» o «se verifica». Cada una debería estar respaldada por datos, pruebas, citas o una explicación técnica suficiente, y expresar de forma precisa sus condiciones de validez.

## 11. Coordinación con los asesores y entrega del documento

### 11.1. Orden de revisión indicado

Carlos indicó que todavía no había revisado el documento y pidió que se le reenviara la **última versión disponible del trabajo de grado**. También aclaró que debe distinguirse del documento del proyecto de investigación, que es un entregable diferente.

El procedimiento acordado durante la reunión fue:

1. Preparar una versión inicial revisada del documento de grado.
2. Enviarla a Carlos para su lectura y correcciones.
3. Aplicar o discutir las observaciones recibidas.
4. Realizar una revisión adicional con el otro profesor.
5. Coordinar una nueva reunión a partir de la lectura del documento.

El profesor inicial insistió en que sus observaciones se consultaran con Carlos. Por ello, las sugerencias de modificación de alcance, metodología o arquitectura deberían recibir especial atención antes de darse por definitivas.

### 11.2. Qué conviene enviar

Lo más útil es enviar una versión coherente, no una colección de borradores inconexos. Debe identificar claramente el alcance de la ISA, las dos microarquitecturas, la plataforma, los métodos de verificación, las métricas comparadas y las limitaciones conocidas. Si existen decisiones técnicas no resueltas, se pueden señalar como pendientes con una explicación breve de su impacto.

## 12. Plan de trabajo priorizado

Esta priorización es una **propuesta de organización derivada de la reunión**; los profesores no establecieron formalmente estos niveles de prioridad.

### Prioridad alta: antes de enviar la versión a Carlos

- [ ] Revisar el manuscrito párrafo por párrafo y justificar la función de cada uno.
- [ ] Corregir referencias ambiguas como «este estudio» e identificar claramente trabajo propio frente a antecedentes.
- [ ] Revisar los antecedentes de 23 instrucciones y retirar los que no tengan utilidad argumentativa real.
- [ ] Verificar que las fuentes bibliográficas correspondan a las afirmaciones que respaldan.
- [ ] Añadir la referencia de la suite RISC-V en su primera explicación pertinente.
- [ ] Eliminar o delimitar afirmaciones que impliquen mediciones de consumo no realizadas.
- [ ] Confirmar el modelo exacto de placa y FPGA y corregir cualquier inconsistencia.
- [ ] Revisar los objetivos para explicar las siglas y mantener solo métricas realmente previstas.
- [ ] Corregir redacción, ortografía, terminología y continuidad de ideas.
- [ ] Enviar a Carlos la última versión del **documento de grado**, no confundirla con la propuesta de investigación.

### Prioridad técnica: resolver antes de cerrar resultados y conclusiones

- [ ] Verificar las características y la capacidad de las memorias internas y externas de la tarjeta.
- [ ] Evaluar la propuesta de lectura síncrona mediante anticipación del siguiente PC.
- [ ] Validar el funcionamiento de saltos, ramificaciones, reset y cambios de flujo con el nuevo esquema de memoria.
- [ ] Comprobar la inferencia real de Block RAM y el impacto en recursos y temporización.
- [ ] Definir y ejecutar un protocolo reproducible para medir ciclos, instrucciones, CPI y tasa de procesamiento.
- [ ] Identificar las rutas críticas reales con análisis temporal de Quartus.
- [ ] Verificar que los programas de evaluación caben en memoria y completan correctamente su ejecución.
- [ ] Precisar cuáles resultados dependen de la FPGA y cuáles describen el comportamiento microarquitectónico.
- [ ] Preparar una demostración verificable del módulo de visualización.

### Prioridad de cierre: antes de la versión final

- [ ] Comprobar que los objetivos corresponden con la metodología, los experimentos y las conclusiones.
- [ ] Interpretar las diferencias entre arquitecturas con criterios de comparabilidad explícitos.
- [ ] Separar resultados propios, antecedentes bibliográficos, hipótesis y trabajo futuro.
- [ ] Revisar nuevamente la coherencia completa sin depender exclusivamente de IA.
- [ ] Incorporar las correcciones y decisiones confirmadas por los asesores.

## 13. Preguntas concretas para discutir con Carlos

1. **Alcance de ISA:** ¿qué instrucciones y extensiones deben considerarse obligatorias para la validación del proyecto, incluyendo el tratamiento de instrucciones de sistema?
2. **Antecedentes:** ¿es preferible eliminar por completo la referencia de 23 instrucciones o conservar alguna parte por una comparación metodológica específica?
3. **Memoria monociclo:** ¿la anticipación del siguiente PC propuesta en la reunión resulta compatible con el diseño actual y con sus saltos y redirecciones?
4. **Equivalencia experimental:** ¿cómo se documentarán las diferencias de implementación de memoria entre el monociclo y el segmentado?
5. **Benchmarks:** ¿cuáles se ejecutarán de forma completa y cuáles deben excluirse o limitarse por capacidad de memoria?
6. **Métricas:** ¿qué definición exacta de CPI, tasa de procesamiento y recursos se adoptará para obtener resultados comparables?
7. **Presentación de Fmax:** ¿cómo se separarán las conclusiones asociadas a la tecnología FPGA de las observaciones microarquitectónicas?
8. **Alcance del documento:** ¿cuáles secciones del trabajo de grado deben completarse antes de la siguiente revisión conjunta?

## 14. Matriz de trazabilidad de las recomendaciones

| Tema | Observación originada en la reunión | Cambio esperado | Evidencia de cierre |
|---|---|---|---|
| Terminología | Traducir *testbenches* y explicar *hazard* | Términos definidos y consistentes | Revisión de objetivos y marco teórico |
| Objetivos | Expandir CPI y revisar *throughput* | Métricas formuladas con claridad | Objetivos corregidos |
| RISC-V tests | Identificar y citar la suite | Referencia asociada al método de verificación | Cita y entrada bibliográfica |
| Justificación | Revisarla después de Carlos | Argumentación alineada con el alcance | Comentarios del asesor incorporados |
| Antecedentes | Cuestionar la utilidad del núcleo de 23 instrucciones | Conservar solo referencias pertinentes | Selección y justificación de fuentes |
| Claridad textual | Evitar «este estudio» ambiguo | Sujeto de cada afirmación identificable | Revisión de párrafos |
| Potencia | No anunciar mediciones no previstas | Delimitación de métricas | Objetivos, método y resultados coherentes |
| Plataforma | Evitar generalizaciones a todas las FPGA | Modelo de hardware explícito | Identificación y configuración verificadas |
| Memoria monociclo | Considerar dirección anticipada para Block RAM | Solución evaluada, no asumida | Simulación, síntesis y pruebas |
| Benchmarks | Verificar viabilidad con capacidad de memoria | Pruebas ejecutables y reproducibles | Mapas de memoria y registros de ejecución |
| Camino crítico | Comprender Fmax mediante retardos de rutas | Análisis temporal fundamentado | Reportes de Quartus |
| Comparación | Distinguir CPI de Fmax dependiente de placa | Interpretación metodológicamente válida | Tablas y discusión de resultados |
| Visualización | Mostrar el módulo que ya funciona | Demostración didáctica comprobable | Pruebas y evidencia visual |
| Revisión editorial | Leer todo el texto y usar IA críticamente | Documento coherente y comprendido | Lectura y corrección final |
| Coordinación | Enviar el documento de grado a Carlos | Primera revisión formal | Versión enviada y observaciones recibidas |

## 15. Criterio final para revisar cada capítulo

Para cada sección del manuscrito conviene responder de forma explícita a cinco preguntas:

1. **Propósito:** ¿qué necesita comprender el lector al terminar esta sección?
2. **Fundamento:** ¿qué referencias, razonamientos o datos sostienen las afirmaciones?
3. **Correspondencia:** ¿lo descrito representa lo que realmente se diseñó, implementó o midió?
4. **Alcance:** ¿qué condiciones, limitaciones o dependencias tecnológicas deben indicarse?
5. **Conexión:** ¿cómo contribuye esta sección a los objetivos y a la comparación de las dos microarquitecturas?

**Resultado esperado:** un documento que no solo describa dos procesadores, sino que justifique las decisiones técnicas, demuestre la corrección funcional, explique el procedimiento experimental y extraiga conclusiones proporcionadas a la evidencia disponible.

---

**Fuente de trabajo:** transcripción de la reunión proporcionada en el archivo `Markdown pegado(1).md`. Las reformulaciones, el plan de prioridades, las preguntas de control y las advertencias de validación técnica fueron organizadas para facilitar su aplicación; no deben confundirse con citas textuales ni con acuerdos adicionales de los profesores.
