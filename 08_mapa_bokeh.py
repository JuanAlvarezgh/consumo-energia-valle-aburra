# -*- coding: utf-8 -*-
"""
Mapa del Valle de Aburrá con Bokeh: mapa_valle_bokeh.html

Todo se arma desde Python, sin escribir JavaScript. Las cuatro capas de medidores
son cuatro glifos separados y se prenden y apagan haciendo clic en la leyenda,
que es una funcion propia de Bokeh (click_policy='hide'): apagando las capas de
recuperados queda a la vista lo que pierde una union por interseccion sola.

Los puntos se dibujan en WebGL, que aguanta las 589.799 direcciones. Las
manzanas van por canvas, que es lo unico que hay para poligonos, asi que se usa
la geometria simplificada a 12 m.
"""
import os
import sys
import pathlib

_raiz = pathlib.Path(sys.executable).parents[1]
os.environ.setdefault('PROJ_DATA', str(_raiz / 'share' / 'proj'))
os.environ.setdefault('GDAL_DATA', str(_raiz / 'apps' / 'gdal' / 'share' / 'gdal'))

import time
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from bokeh.io import save
from bokeh.layouts import column
from bokeh.models import (ColorBar, ColumnDataSource, Div, FixedTicker, HoverTool,
                          LabelSet, LinearColorMapper, MultiPolygons, Range1d)
from bokeh.plotting import figure

BASE = pathlib.Path(__file__).resolve().parent
SALIDA = str(BASE)
GPKG = SALIDA + "/manzanas_medidores.gpkg"
DESTINO = SALIDA + "/mapa_valle_bokeh.html"
UMBRAL = 7.5
BUSCA = 17.0
TOLERANCIA = 18.0          # simplificacion de las manzanas, en metros
# Las direcciones son 14 de los 28 MB del archivo: Bokeh guarda el texto sin
# comprimir. En False el mapa pesa la mitad y el globo muestra solo las cifras.
DIRECCIONES = True

PAPEL = '#f7f8f4'
TINTA = '#1d231f'
TINTA_2 = '#565f56'
BORDE = '#8f978d'
MANZANA = '#dfe2da'   # manzana sin dato de consumo
COBRE = ['#cfa243', '#b8871f', '#9e6c0d', '#82550a', '#653d07', '#492905']
PETROLEO = '#00849b'
CAPAS = [('Dentro de la manzana', PETROLEO), ('Recuperado hasta 5 m', '#b07406'),
         ('Recuperado de 5 a 7,5 m', '#653d07'), ('Sin asignar', TINTA_2)]
MUNICIPIOS = {'05001': 'Medellín', '05079': 'Barbosa', '05088': 'Bello',
              '05129': 'Caldas', '05212': 'Copacabana', '05266': 'Envigado',
              '05308': 'Girardota', '05360': 'Itagüí', '05380': 'La Estrella',
              '05631': 'Sabaneta'}
NOMBRE_FUENTE = {'Medellin': 'Medellín', 'Itagui': 'Itagüí'}

t0 = time.time()
def log(m):
    print('[%5.1fs] %s' % (time.time() - t0, m), flush=True)


# ------------------------------------------------------------------ datos
manz = gpd.read_file(GPKG, layer='manzanas_medidores')
med = pd.read_csv(SALIDA + '/medidores_asignados.csv', low_memory=False,
                  usecols=['X', 'Y', 'Categoria', 'Csmo_Prom', 'ambiguo',
                           'Direccion', 'N_Mpio'])
punto = med.groupby(['X', 'Y'], sort=False).agg(
    n=('Categoria', 'size'), amb=('ambiguo', 'max'),
    direccion=('Direccion', 'first'), mpio=('N_Mpio', 'first')).reset_index()
log('manzanas: %d | direcciones: %d' % (len(manz), len(punto)))

arbol = shapely.STRtree(manz.geometry.values)
pts = shapely.points(punto.X.values, punto.Y.values)
i_pt, i_mz = arbol.query(pts, predicate='dwithin', distance=BUSCA)
pares = pd.DataFrame({'pt': i_pt, 'mz': i_mz,
                      'd': shapely.distance(pts[i_pt], manz.geometry.values[i_mz])})
pares = pares.sort_values(['pt', 'd'], kind='stable').drop_duplicates('pt', keep='first')
punto['d'] = np.inf
punto.loc[pares.pt.values, 'd'] = pares.d.values
log('distancia al borde resuelta')

# origen: en coordenadas absolutas EPSG:9377 los float de 32 bits perderian
# medio metro de precision, asi que se dibuja relativo a la esquina del valle
ox, oy = np.floor(min(punto.X.min(), manz.total_bounds[0])), np.floor(min(punto.Y.min(), manz.total_bounds[1]))
punto['x'] = (punto.X - ox).astype('float32')
punto['y'] = (punto.Y - oy).astype('float32')
punto['mpio'] = punto.mpio.map(NOMBRE_FUENTE).fillna(punto.mpio)
punto['capa'] = np.select(
    [punto.d == 0, punto.d <= 5, punto.d <= UMBRAL],
    [0, 1, 2], default=3)
punto['dist'] = np.where(np.isfinite(punto.d), punto.d.round(1), np.nan)

# ------------------------------------------------------------- manzanas
codigo = manz.MPIO_CDPMP.astype(str).str.zfill(5)
manz['municipio'] = codigo.map(MUNICIPIOS)
xs, ys = [], []
for g in manz.geometry.values:
    s = g.simplify(TOLERANCIA)
    partes = s.geoms if s.geom_type == 'MultiPolygon' else [s]
    ax, ay = [], []
    for p in partes:
        c = np.asarray(p.exterior.coords)
        ax.append((c[:, 0] - ox).tolist())
        ay.append((c[:, 1] - oy).tolist())
    xs.append([ax])
    ys.append([ay])
log('geometria simplificada: %d vertices' % sum(len(a) for x in xs for b in x for a in b))

fuente_manz = ColumnDataSource(dict(
    xs=xs, ys=ys,
    codigo=manz.COD_DANE_A, municipio=manz.municipio,
    medidores=manz.medidores.fillna(0).astype(int),
    viviendas=manz.TVIVIENDA.fillna(0).astype(int),
    consumo=manz.consumo_mediana.round(0),
    consumo_txt=np.where(manz.consumo_mediana.notna(),
                         manz.consumo_mediana.round(0).astype('Int64').astype(str) + ' kWh',
                         'sin dato'),
    estrato=manz.estrato_moda.fillna(0).astype(int),
    razon=manz.med_x_vivienda.fillna(0).round(2),
))

# ---------------------------------------------------------------- figura
valores = manz.consumo_mediana.dropna()
cortes = np.unique(np.round(np.quantile(valores, np.linspace(0, 1, 7))))
mapeo = LinearColorMapper(palette=COBRE[:len(cortes) - 1],
                          low=cortes[0], high=cortes[-1], nan_color=MANZANA)

ancho_valle = max(manz.total_bounds[2], punto.X.max()) - ox
alto_valle = max(manz.total_bounds[3], punto.Y.max()) - oy
p = figure(width=1180, height=820, match_aspect=True,
           x_range=Range1d(0, ancho_valle), y_range=Range1d(0, alto_valle),
           tools='pan,wheel_zoom,box_zoom,reset,save', active_scroll='wheel_zoom',
           background_fill_color=PAPEL, border_fill_color=PAPEL,
           outline_line_color=BORDE, output_backend='webgl')
p.axis.visible = False
p.grid.visible = False
p.toolbar.logo = None

manzanas = p.add_glyph(fuente_manz, MultiPolygons(
    xs='xs', ys='ys', fill_color={'field': 'consumo', 'transform': mapeo},
    line_color=BORDE, line_width=0.4, fill_alpha=0.9))

for k, (nombre, color) in enumerate(CAPAS):
    sub = punto[punto.capa == k]
    datos = dict(
        x=sub.x.values, y=sub.y.values,
        n=sub.n.values.astype('int16'),
        dist=sub.dist.values.astype('float32'),
        amb=sub.amb.values.astype('uint8'),
    )
    if DIRECCIONES:
        datos['direccion'] = sub.direccion.fillna('sin dirección').values
    fuente = ColumnDataSource(datos)
    r = p.scatter('x', 'y', source=fuente, size=3.4, color=color,
                  line_color=None, alpha=0.85, legend_label=nombre)
    if k == 0:
        medidor = r
    log('capa %s: %d direcciones' % (nombre, len(sub)))

p.add_tools(HoverTool(renderers=[manzanas], attachment='right', tooltips=[
    ('Manzana', '@codigo'), ('Municipio', '@municipio'),
    ('Medidores', '@medidores{0,0}'), ('Viviendas censadas', '@viviendas{0,0}'),
    ('Medidores por vivienda', '@razon'), ('Consumo mediano', '@consumo_txt'),
    ('Estrato', '@estrato')]))
globo_punto = ([('Dirección', '@direccion')] if DIRECCIONES else []) + [
    ('Medidores aquí', '@n'), ('Distancia al borde', '@dist{0.0} m'),
    ('Ambiguo entre dos manzanas', '@amb{0}')]
p.add_tools(HoverTool(renderers=[r for r in p.renderers if r is not manzanas],
                      attachment='right', tooltips=globo_punto))

# --------------------------------------------------- municipios y leyenda
anclas = punto.groupby('mpio').agg(
    x=('x', 'median'), y=('y', 'median'), n=('n', 'sum')).reset_index()
p.add_layout(LabelSet(
    x='x', y='y', text='mpio', source=ColumnDataSource(anclas),
    text_font_size='11px', text_color=TINTA, text_align='center',
    text_font_style='bold', background_fill_color=PAPEL, background_fill_alpha=0.7))

p.add_layout(ColorBar(
    color_mapper=mapeo, title='Consumo mediano por manzana, kWh/mes',
    ticker=FixedTicker(ticks=cortes.tolist()), width=12,
    background_fill_color=PAPEL, major_label_text_color=TINTA_2,
    title_text_color=TINTA_2, title_text_font_style='normal'), 'right')

p.legend.location = 'top_left'
p.legend.click_policy = 'hide'
p.legend.background_fill_color = PAPEL
p.legend.background_fill_alpha = 0.85
p.legend.border_line_color = BORDE
p.legend.label_text_font_size = '11px'
p.legend.label_text_color = TINTA_2
p.legend.title = 'Clic para apagar una capa'
p.legend.title_text_font_style = 'normal'
p.legend.title_text_color = TINTA_2

cifras = punto.groupby('capa').n.sum()
total = int(cifras.sum())
encabezado = Div(text="""
<div style="font-family:'Franklin Gothic Medium','Segoe UI',sans-serif;color:%s">
  <div style="font-size:21px">Valle de Aburrá, medidor por medidor</div>
  <div style="font-family:Consolas,monospace;font-size:12px;color:%s;margin-top:3px">
    %s medidores &middot; %s direcciones &middot; %s manzanas &middot;
    dentro %s &middot; recuperados %s &middot; sin asignar %s &middot; cobertura %.1f %%
  </div>
</div>""" % (TINTA, TINTA_2,
             f'{total:,}'.replace(',', '.'),
             f'{len(punto):,}'.replace(',', '.'),
             f'{len(manz):,}'.replace(',', '.'),
             f'{int(cifras.get(0, 0)):,}'.replace(',', '.'),
             f'{int(cifras.get(1, 0) + cifras.get(2, 0)):,}'.replace(',', '.'),
             f'{int(cifras.get(3, 0)):,}'.replace(',', '.'),
             100 * (total - cifras.get(3, 0)) / total),
    width=1180)

save(column(encabezado, p), filename=DESTINO, title='Valle de Aburrá, medidor por medidor',
     resources='inline')
log('escrito %s (%.1f MB)' % (DESTINO, os.path.getsize(DESTINO) / 1e6))
