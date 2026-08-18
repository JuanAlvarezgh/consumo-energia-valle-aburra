# -*- coding: utf-8 -*-
"""
Arma y ejecuta analisis_energia.ipynb: seis preguntas, seis graficas.

El notebook queda con las salidas dentro, asi que se lee sin correrlo. Cada celda
imprime su hallazgo con las cifras recalculadas, y guarda su grafica en graficas/.
"""
import os
import sys
import pathlib

_raiz = pathlib.Path(sys.executable).parents[1]
os.environ.setdefault('PROJ_DATA', str(_raiz / 'share' / 'proj'))
os.environ.setdefault('GDAL_DATA', str(_raiz / 'apps' / 'gdal' / 'share' / 'gdal'))

import nbformat as nbf
from nbclient import NotebookClient

SALIDA = pathlib.Path(__file__).resolve().parent
DESTINO = SALIDA / 'analisis_energia.ipynb'

PREPARACION = r'''
import pathlib
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

RUTA = pathlib.Path.cwd()
GRAFICAS = RUTA / "graficas"
GRAFICAS.mkdir(exist_ok=True)

PAPEL, TINTA, TINTA_2, LINEA = "#f1f2ee", "#1d231f", "#565f56", "#d3d7cf"
COBRE = ["#cfa243", "#b8871f", "#9e6c0d", "#82550a", "#653d07", "#492905"]
PETROLEO = "#00849b"
for arch in ["framd.ttf", "corbel.ttf", "consola.ttf"]:
    ruta = pathlib.Path("C:/Windows/Fonts") / arch
    if ruta.exists():
        font_manager.fontManager.addfont(str(ruta))
mpl.rcParams.update({
    "figure.facecolor": PAPEL, "axes.facecolor": PAPEL, "savefig.facecolor": PAPEL,
    "font.family": "Corbel", "font.size": 10, "text.color": TINTA,
    "axes.edgecolor": TINTA_2, "axes.labelcolor": TINTA_2,
    "xtick.color": TINTA_2, "ytick.color": TINTA_2, "figure.dpi": 110,
})
TIT = {"fontname": "Franklin Gothic Medium"}
DAT = {"fontname": "Consolas"}
MILES = FuncFormatter(lambda v, _: f"{int(v):,}".replace(",", "."))

def marco(ax, titulo, x=None, y=None, eje_y_miles=True):
    ax.set_title(titulo, loc="left", fontsize=14, pad=12, **TIT)
    if x:
        ax.set_xlabel(x)
    if y:
        ax.set_ylabel(y)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=LINEA, lw=0.9)
    ax.set_axisbelow(True)
    if eje_y_miles:
        ax.yaxis.set_major_formatter(MILES)

def guardar(fig, nombre):
    fig.tight_layout()
    fig.savefig(GRAFICAS / nombre, dpi=200)

def n(x, dec=0):
    return f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")

from IPython.display import Markdown

def fragmento(archivo, desde, hasta):
    """Muestra el trozo del script que va entre dos anclas de texto."""
    lineas = (RUTA / archivo).read_text(encoding="utf-8").split("\n")
    i = next(k for k, l in enumerate(lineas) if desde in l)
    j = next(k for k, l in enumerate(lineas[i + 1:], i + 1) if hasta in l)
    codigo = "\n".join(lineas[i:j]).rstrip()
    return Markdown("```python\n" + codigo + "\n```")

med = pd.read_csv(RUTA / "medidores_asignados.csv", low_memory=False)
manz = pd.read_csv(RUTA / "manzanas_amva_medidores.csv", low_memory=False)
MPIO = {"Medellin": "Medellín", "Itagui": "Itagüí"}
med["N_Mpio"] = med.N_Mpio.replace(MPIO)

# El cero de Csmo_Prom es dato censurado, no consumo cero: se trata como ausente.
med["lectura"] = med.Csmo_Prom.replace(0, np.nan)
asignados = med[med.metodo != "no_asignado"]
res = asignados[(asignados.Categoria == "RESIDENCIAL") & (asignados.ESTRATO.between(1, 6))]

print("medidores:", n(len(med)), "| asignados a una manzana:", n(len(asignados)),
      "| residenciales con lectura:", n(int(res.lectura.notna().sum())))
'''

PROCEDENCIA = ('De dónde salen los datos', '\nimport subprocess\nimport time\n\nORIGEN = RUTA.parent / "UrbanAnalysis.gdb"\nARCHIVOS = ["manzanas_medidores.gpkg", "medidores_asignados.csv",\n            "manzanas_amva_medidores.csv"]\n\n# Si falta alguno se reconstruye desde la geodatabase: son 50 segundos.\nfaltan = [a for a in ARCHIVOS if not (RUTA / a).exists()]\nif faltan:\n    print("reconstruyendo:", ", ".join(faltan))\n    subprocess.run([sys.executable, str(RUTA / "01_asignar_medidores.py")], check=True)\n\nprint("origen:", ORIGEN.name, "|", n(sum(f.stat().st_size for f in ORIGEN.iterdir()) / 1e6, 1), "MB")\nfor a in ARCHIVOS:\n    ruta = RUTA / a\n    print("  %-28s %8s MB   %s" % (a, n(ruta.stat().st_size / 1e6, 1),\n                                   time.strftime("%Y-%m-%d %H:%M", time.localtime(ruta.stat().st_mtime))))\n')
BLOQUES_METODO = [
    ("""El punto de una dirección cae sobre la fachada, no dentro del predio. Por eso una
unión espacial por intersección, que es lo que uno haría por defecto, pierde
**465.499 medidores, el 34 % del total**.

La regla que resuelve eso: **un medidor cuenta para una manzana si cae dentro de
ella o si está a 7,5 m o menos de su borde**, medido al borde y no al centroide.
El resto de esta sección es cómo se programa esa regla, paso por paso.

### 1. Leer las dos capas, ya filtradas

El `where` filtra al leer, no después: en vez de cargar las 504.996 manzanas del
país y botar el 96 %, trae solo las 22.000 del valle. El `force_2d` quita las
coordenadas Z y M de la capa de EPM, que vienen con basura y hacen fallar varias
operaciones espaciales.""",
     'fragmento("01_asignar_medidores.py", "campos_censo = ", "log(" + chr(34) + "medidores:")'),

    ("""### 2. Agrupar por coordenada

Este es el paso que más trabajo ahorra. En un edificio de 40 apartamentos los 40
contadores tienen la misma dirección, y por lo tanto el mismo punto: calcular 40
veces la misma distancia es desperdicio. Los **1.362.005 medidores se reducen a
589.799 puntos distintos**, menos de la mitad.

Además evita un error: si se calcularan por separado, dos contadores del mismo
edificio podrían terminar en manzanas distintas.""",
     'fragmento("01_asignar_medidores.py", "coord = med.groupby(", "log(" + chr(34) + "coordenadas unicas")'),

    ("""### 3. Preguntar qué manzanas están cerca, y medir

Un `STRtree` es un índice espacial y funciona como el índice de un libro. Sin él
habría que comparar cada punto con cada manzana: 589.799 x 22.000 = **13.000
millones de comparaciones**. Con el índice uno pregunta *cuáles manzanas están a
menos de 9,5 m de este punto* y devuelve una o dos. Salen 778.128 parejas y tarda
4 segundos.

Después `shapely.distance` mide, para cada pareja, la **distancia exacta del punto
al borde** de esa manzana. Al borde, no al centro.

¿Por qué 9,5 y no 7,5? Porque es el umbral más 2 m de margen, y esos 2 m se
necesitan en el paso siguiente.""",
     'fragmento("01_asignar_medidores.py", "arbol = shapely.STRtree", "log(" + chr(34) + "parejas punto-manzana")'),

    ("""### 4. Escoger la manzana y clasificar

Se ordenan las parejas por distancia y se toman **las dos primeras** de cada
punto. La primera es la manzana asignada. La segunda sirve para saber si esa
decisión es confiable: si está a menos de 2 m de diferencia, el medidor está sobre
el eje de la vía, gana una manzana por centímetros y queda marcado como `ambiguo`.

Las tres clases: distancia cero es `dentro`, hasta 7,5 m es `cercano`, más lejos
es `no_asignado` y no se fuerza. Un punto dentro del polígono da distancia cero y
gana sin competencia, así que la misma línea resuelve los dos casos.""",
     'fragmento("01_asignar_medidores.py", "pares = (pd.DataFrame", "log(" + chr(34) + "coordenadas -> dentro")'),

    ("""### 5. Devolver el resultado a cada medidor

Un `merge` por coordenada reparte la respuesta a los 1.362.005 medidores: los 40
contadores del edificio reciben la misma manzana. Aquí queda listo el contenido de
`medidores_asignados.csv`.""",
     'fragmento("01_asignar_medidores.py", "med = med.merge(coord[", "total = len(med)")'),

    ("""### 6. Contar por manzana y escribir los archivos

Para el segundo CSV se agrupa al revés, por `cod_manzana`, y se pega el resultado
a la tabla de manzanas con sus variables del censo.""",
     'fragmento("01_asignar_medidores.py", "g = pd.DataFrame({", "out = manz.merge(g")'),

    ("""`drop(columns="geometry")` es lo que convierte una capa geográfica en una tabla
común: se le quita la geometría y queda un CSV que abre pandas, Excel o Power BI.
El GPKG guarda lo mismo pero **con** geometría, que es lo que leen los mapas.""",
     'fragmento("01_asignar_medidores.py", "gpkg = SALIDA", "archivos escritos")'),
]

CELDAS = [
    ('¿Qué estrato gasta más luz?', '''
serie = res.groupby("ESTRATO").lectura.median()
promedio = res.groupby("ESTRATO").lectura.mean()

fig, ax = plt.subplots(figsize=(7.6, 4.2))
ax.bar(serie.index, serie.values, width=0.62, color=COBRE[2], zorder=2)
for e, v in serie.items():
    ax.text(e, v + 4, "%.0f" % v, ha="center", va="bottom", fontsize=10, **DAT)
ax.set_xticks(serie.index)
ax.set_ylim(0, serie.max() * 1.16)
marco(ax, "Consumo mediano por estrato", x="Estrato", y="kWh / mes")
guardar(fig, "1_consumo_por_estrato.png")
plt.show()

print("El estrato 6 gasta %s kWh al mes contra %s del estrato 1: %s veces más."
      % (n(serie.loc[6]), n(serie.loc[1]), n(serie.loc[6] / serie.loc[1], 2)))
print("En promedio, no en mediana, el 6 llega a %s kWh." % n(promedio.loc[6]))
'''),

    ('¿Cuánto gasta una manzana típica?', '''
mz = manz[manz.med_residencial >= 3].copy()
mediana = mz.consumo_mediana.median()

fig, ax = plt.subplots(figsize=(7.6, 4.2))
ax.hist(mz.consumo_mediana, bins=np.arange(0, 401, 10), color=COBRE[1],
        edgecolor=PAPEL, lw=0.7, zorder=2)
ax.axvline(mediana, color=PETROLEO, lw=1.6, zorder=3)
ax.text(mediana + 5, ax.get_ylim()[1] * 0.94, "mediana %s kWh" % n(mediana),
        color=PETROLEO, fontsize=9.5, va="top", **DAT)
ax.set_xlim(0, 400)
marco(ax, "Consumo mediano de la manzana", x="kWh / mes por medidor residencial",
      y="Manzanas")
guardar(fig, "2_consumo_por_manzana.png")
plt.show()

print("De las %s manzanas con al menos tres medidores residenciales, la mitad está"
      " entre %s y %s kWh por medidor."
      % (n(len(mz)), n(mz.consumo_mediana.quantile(0.25)),
         n(mz.consumo_mediana.quantile(0.75))))
print("El gasto de una manzana entera suma en mediana %s kWh al mes."
      % n((mz.consumo_mediana * mz.med_residencial).median()))
'''),

    ('¿Dónde se gasta más por medidor?', '''
por_mpio = res.groupby("N_Mpio").lectura.median().sort_values()

fig, ax = plt.subplots(figsize=(7.6, 4.6))
ax.barh(por_mpio.index, por_mpio.values, height=0.66, color=COBRE[2], zorder=2)
for i, (m, v) in enumerate(por_mpio.items()):
    ax.text(v + 2, i, "%.0f" % v, va="center", fontsize=9.5, **DAT)
ax.set_xlim(0, por_mpio.max() * 1.14)
marco(ax, "Consumo mediano por municipio", x="kWh / mes por medidor residencial",
      eje_y_miles=False)
ax.grid(axis="x", color=LINEA, lw=0.9)
ax.grid(axis="y", visible=False)
guardar(fig, "3_consumo_por_municipio.png")
plt.show()

print("%s encabeza con %s kWh y %s cierra con %s."
      % (por_mpio.index[-1], n(por_mpio.iloc[-1]), por_mpio.index[0], n(por_mpio.iloc[0])))
'''),

    ('¿Cuánta energía consume cada municipio en total?', '''
total = asignados.groupby("N_Mpio").lectura.sum().sort_values() / 1e6

fig, ax = plt.subplots(figsize=(7.6, 4.6))
ax.barh(total.index, total.values, height=0.66, color=COBRE[3], zorder=2)
for i, (m, v) in enumerate(total.items()):
    ax.text(v + total.max() * 0.012, i, n(v, 1), va="center", fontsize=9.5, **DAT)
ax.set_xlim(0, total.max() * 1.14)
marco(ax, "Gasto total de energía", x="GWh / mes", eje_y_miles=False)
ax.grid(axis="x", color=LINEA, lw=0.9)
ax.grid(axis="y", visible=False)
guardar(fig, "4_gasto_total_por_municipio.png")
plt.show()

print("El valle suma %s GWh al mes. Medellín pesa el %s %% de ese total."
      % (n(total.sum(), 1), n(100 * total.loc["Medellín"] / total.sum(), 1)))
print("La cifra es un piso: la fuente recorta el consumo en 1.000 kWh por medidor.")
'''),

    ('¿Qué tipo de instalación gasta más?', '''
cat = asignados.groupby("Categoria").agg(
    mediana=("lectura", "median"), medidores=("lectura", "size"),
    con_lectura=("lectura", "count"))
cat = cat[cat.con_lectura >= 500].sort_values("mediana")

fig, ax = plt.subplots(figsize=(7.6, 4))
ax.barh(cat.index.str.capitalize(), cat.mediana, height=0.62, color=COBRE[2], zorder=2)
for i, v in enumerate(cat.mediana):
    ax.text(v + 4, i, "%.0f" % v, va="center", fontsize=9.5, **DAT)
ax.set_xlim(0, cat.mediana.max() * 1.16)
marco(ax, "Consumo mediano por categoría", x="kWh / mes", eje_y_miles=False)
ax.grid(axis="x", color=LINEA, lw=0.9)
ax.grid(axis="y", visible=False)
guardar(fig, "5_consumo_por_categoria.png")
plt.show()

print(cat.assign(sin_lectura_pct=(100 * (1 - cat.con_lectura / cat.medidores)).round(1))
        .to_string())
print("En industrial y oficial más de la mitad de los medidores llega sin lectura,"
      " así que su mediana se calcula sobre los pocos que sí la traen.")
'''),

    ('¿Cuántos medidores tiene una manzana?', '''
con = manz[manz.medidores > 0]
mediana = con.medidores.median()

fig, ax = plt.subplots(figsize=(7.6, 4.2))
ax.hist(con.medidores.clip(upper=300), bins=np.arange(0, 305, 10),
        color=COBRE[1], edgecolor=PAPEL, lw=0.7, zorder=2)
ax.axvline(mediana, color=PETROLEO, lw=1.6, zorder=3)
ax.text(mediana + 4, ax.get_ylim()[1] * 0.94, "mediana %s" % n(mediana),
        color=PETROLEO, fontsize=9.5, va="top", **DAT)
ax.set_xlim(0, 300)
marco(ax, "Medidores por manzana", x="Medidores asignados", y="Manzanas")
guardar(fig, "6_medidores_por_manzana.png")
plt.show()

print("%s de %s manzanas tienen al menos un medidor. La mediana es %s medidores"
      " y el máximo %s." % (n(len(con)), n(len(manz)), n(mediana), n(con.medidores.max())))
print("Frente al censo, la razón mediana es de %s medidores por vivienda censada."
      % n(manz[manz.TVIVIENDA > 0].med_x_vivienda.median(), 2))
'''),
]

CIERRE = ('Cifras de referencia', '''
resumen = pd.DataFrame([
    ("Medidores en la geodatabase", n(len(med))),
    ("Asignados a una manzana", "%s (%s %%)" % (n(len(asignados)),
                                                n(100 * len(asignados) / len(med), 1))),
    ("Direcciones distintas", n(med[["X", "Y"]].drop_duplicates().shape[0])),
    ("Manzanas del Valle de Aburrá", n(len(manz))),
    ("Manzanas con medidores", n(int((manz.medidores > 0).sum()))),
    ("Consumo mediano residencial", n(res.lectura.median()) + " kWh/mes"),
    ("Gasto total del valle", n(asignados.lectura.sum() / 1e6, 1) + " GWh/mes"),
    ("Medidores sin lectura", "%s (%s %%)" % (n(int(med.Csmo_Prom.eq(0).sum())),
                                              n(100 * med.Csmo_Prom.eq(0).mean(), 1))),
    ("Asignación ambigua entre dos manzanas", n(int(med.ambiguo.sum()))),
], columns=["", "valor"])
resumen.style.hide(axis="index")
''')

nb = nbf.v4.new_notebook()
nb.cells.append(nbf.v4.new_markdown_cell(
    '# Consumo de energía por manzana en el Valle de Aburrá\n\n'
    'Medidores de EPM de `UrbanAnalysis.gdb` asignados a las manzanas del Marco '
    'Geoestadístico Nacional: dentro del polígono o a 7,5 m o menos de su borde. '
    'Los medidores sin lectura no entran en los promedios.'))
nb.cells.append(nbf.v4.new_code_cell(PREPARACION.strip()))

nb.cells.append(nbf.v4.new_markdown_cell('## ' + PROCEDENCIA[0]))
nb.cells.append(nbf.v4.new_code_cell(PROCEDENCIA[1].strip()))
for texto, codigo in BLOQUES_METODO:
    nb.cells.append(nbf.v4.new_markdown_cell(texto))
    nb.cells.append(nbf.v4.new_code_cell(codigo.strip()))
nb.cells.append(nbf.v4.new_markdown_cell("""### Lo que sale de todo esto

**896.506** medidores caen dentro de su manzana, **407.237** se recuperan por cercanía
y **58.262** quedan sin asignar, casi todos rurales. Cobertura: **95,7 %**.

Dos cosas sostienen el resultado:

**Por qué 7,5 m y no otro número.** Sale de medir la calle, no de una preferencia.
Sumando la distancia a la manzana más cercana y a la segunda para los medidores que
están en la vía, el corredor típico del valle mide **11,6 m de borde a borde**, con
cuartil inferior en 9,0 m. La media calzada son 5,8 m: a más de ocho metros el medidor
ya cruzó el eje y probablemente es de la manzana de enfrente.

**Cómo se sabe que quedó bien.** Con el censo, que es un dato independiente. Si la
asignación es correcta, los medidores residenciales de una manzana deben parecerse a
las viviendas censadas ahí. Contando solo los de adentro salen **0,55** medidores por
vivienda, que es imposible; con los recuperados sube a **0,91**, casi uno a uno, y la
correlación pasa de 0,702 a 0,748. Eso prueba que los recuperados sí pertenecen a esa
manzana y que no se están inflando conteos."""))

for titulo, codigo in CELDAS:
    nb.cells.append(nbf.v4.new_markdown_cell('## ' + titulo))
    nb.cells.append(nbf.v4.new_code_cell(codigo.strip()))
nb.cells.append(nbf.v4.new_markdown_cell('## ' + CIERRE[0]))
nb.cells.append(nbf.v4.new_code_cell(CIERRE[1].strip()))

nb.metadata.kernelspec = {'name': 'python3', 'display_name': 'Python 3',
                          'language': 'python'}
nb.metadata.language_info = {'name': 'python', 'version': sys.version.split()[0]}

print('ejecutando el notebook...')
NotebookClient(nb, timeout=900, kernel_name='python3',
               resources={'metadata': {'path': str(SALIDA)}}).execute()
nbf.write(nb, str(DESTINO))
print('escrito %s (%.2f MB)' % (DESTINO, DESTINO.stat().st_size / 1e6))
