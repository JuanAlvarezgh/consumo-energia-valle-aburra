# Consumo de energía por manzana en el Valle de Aburrá

Asignación de 1.362.005 medidores de energía de EPM a las 22.000 manzanas del Marco
Geoestadístico Nacional del DANE, y análisis del consumo resultante por manzana,
estrato y municipio.

## El problema

Los medidores están geocodificados por dirección, y la dirección cae sobre la fachada
del predio, no dentro de él. Una unión espacial por intersección, que es lo que uno
haría por defecto, pierde **465.499 medidores: el 34 % del total**. La pérdida no es
aleatoria, se concentra en predios de fachada corta y manzanas de trama antigua, así
que cualquier indicador por manzana calculado así queda sesgado.

## La regla

Un medidor cuenta para una manzana si cae dentro del polígono **o si está a 7,5 m o
menos de su borde**, medido al borde y no al centroide, con distancia exacta de punto a
segmento.

El umbral sale de la geometría de la calle. Sumando la distancia a la manzana más
cercana y a la segunda para los medidores que están en la vía, el corredor típico del
valle mide 11,6 m de borde a borde, con cuartil inferior en 9,0 m. La media calzada son
5,8 m: un medidor a más de ocho metros de su manzana ya pasó el eje de la vía y
probablemente pertenece a la de enfrente.

## Resultado

| | Medidores | |
|---|---|---|
| Dentro del polígono | 896.506 | 65,8 % |
| Recuperados por cercanía | 407.237 | 29,9 % |
| Sin asignar | 58.262 | 4,3 % |
| **Cobertura** | **1.303.743** | **95,7 %** |

De los que quedan sin asignar, 41.419 están en suelo rural, donde la manzana urbana del
MGN no existe.

## Validación

La prueba independiente es el censo: si la asignación es correcta, los medidores
residenciales de una manzana deben parecerse a las viviendas censadas ahí.

| Método | Correlación con TVIVIENDA | Mediana de medidores por vivienda |
|---|---|---|
| Solo los que caen dentro | 0,702 | 0,55 |
| Dentro más cercanos hasta 7,5 m | 0,748 | **0,91** |

La razón pasa de 0,55 a 0,91 medidores por vivienda censada. Ese salto es la prueba de
que los recuperados pertenecen a la manzana a la que se les asignó.

## El empate, y cómo lo rompe la dirección

51.155 medidores, el 3,8 % del total, tienen una segunda manzana a menos de 2 m de
diferencia: están sobre el eje de la vía o en una esquina, y ahí la geometría decide por
centímetros.

Para esos casos entra la nomenclatura. En `CL 88 A CR 74 -4` la placa indica el costado
de la vía: medido sobre los medidores que caen dentro de una manzana, el **83 % de los
grupos vía-manzana tiene placas de una sola paridad**. La evidencia se arma con esos
medidores, que no admiten duda, y con ella se rompe el empate.

| | |
|---|---|
| Acierto de la regla, medido donde la geometría sí decide | 85 % |
| Ambiguos que resuelve | 16.144 de 51.155 |
| Ambiguos que quedan marcados | 35.011 |

Como en un empate la geometría acierta el 50 %, una regla del 85 % es una mejora real.
Los 35.011 que no se resuelven quedan con la bandera `ambiguo`. En el mapa no cuentan
para ninguna manzana, y una casilla permite dárselos a la más cercana para ver cuánto
pesa esa decisión: 1.269.102 medidores contra 1.304.113, y 19.322 manzanas contra
19.448.

## Trampas del dato de consumo

- El campo `Csmo_Prom` está censurado en 1.000 kWh: el máximo de toda la tabla es 999,9
  incluso en la categoría industrial. Cualquier suma de gasto es un piso, no el total.
- 61.339 medidores residenciales vienen en cero, y en industrial y oficial la proporción
  llega al 53 % y al 61 %. Ese cero es dato faltante, no consumo nulo. Todos los
  promedios de este trabajo lo tratan como ausente.
- El campo `ESTRATO` trae el código 11 en 22.306 registros, todos no residenciales: es
  el código de sin estrato y hay que excluirlo antes de agrupar.

## Contenido

| Archivo | Qué es |
|---|---|
| `01_asignar_medidores.py` | Lee la geodatabase, asigna, valida contra el censo y agrega por manzana |
| `08_mapa_bokeh.py` | Mapa interactivo del valle con Bokeh |
| `analisis_energia.ipynb` | El análisis: el método paso por paso y seis preguntas con sus gráficas, con las salidas dentro |
| `graficas/` | Las gráficas en PNG |
| `mapa_valle.html` | Mapa principal: 22.000 manzanas y 589.799 direcciones. El umbral se cambia en vivo y las manzanas se vuelven a agregar con él; los medidores se pueden ocultar |
| `mapa_valle_bokeh.html` | El mismo mapa hecho con Bokeh, con las capas de asignación conmutables desde la leyenda |
| `manzanas_amva_medidores.csv` | Una fila por manzana: consumo agregado y variables del censo |

Los dos archivos pesados que produce el pipeline, `manzanas_medidores.gpkg` y
`medidores_asignados.csv`, no están en el repositorio por tamaño. El notebook los
reconstruye desde la geodatabase en la primera celda.

## Datos de origen

`UrbanAnalysis.gdb`, geodatabase de ESRI con las instalaciones eléctricas de EPM
(`IEpm_DensUrbam`) y las manzanas censales del DANE (`MGN_ANM_MANZANA`). Sistema de
referencia MAGNA-SIRGAS / Origen Nacional, EPSG:9377. No se incluye en el repositorio.

## Entorno

Python 3.12 con geopandas, shapely, pyogrio, pandas, matplotlib y bokeh. Los
scripts se corren con el intérprete que trae QGIS, que ya incluye la parte geoespacial.
El paso pesado, 1,36 millones de puntos contra 22.000 polígonos, tarda 50 segundos.
