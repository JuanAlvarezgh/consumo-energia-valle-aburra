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

# La geodatabase se busca al lado de esta carpeta; los resultados se escriben aqui.
BASE = pathlib.Path(__file__).resolve().parent
GDB = str(BASE.parent / 'UrbanAnalysis.gdb')
SALIDA = str(BASE)
UMBRAL  = 7.5   # metros: media calzada del Valle de Aburra (corredor mediano 11,6 m)
AMBIGUO = 2.0   # si la segunda manzana esta a menos de esto, la asignacion es dudosa
MUNICIPIOS = ['05001', '05079', '05088', '05129', '05212',
              '05266', '05308', '05360', '05380', '05631']

t0 = time.time()


def log(msg):
    print("[%6.1fs] %s" % (time.time() - t0, msg), flush=True)


# ---------------------------------------------------------------- manzanas
campos_censo = ['COD_DANE_A', 'MPIO_CDPMP', 'CLAS_CCDGO', 'TVIVIENDA', 'TP16_HOG',
                'TP27_PERSO', 'TP19_EE_1'] + ['TP19_EE_E%d' % e for e in range(1, 7)]
manz = gpd.read_file(
    GDB, layer='MGN_ANM_MANZANA', columns=campos_censo,
    where="MPIO_CDPMP IN (%s)" % ','.join("'%s'" % m for m in MUNICIPIOS))
manz['area_ha'] = manz.area / 10_000
log("manzanas del Valle de Aburra: %d" % len(manz))

# ---------------------------------------------------------------- medidores
med = gpd.read_file(GDB, layer='IEpm_DensUrbam', columns=[
    'Direccion', 'Categoria', 'Csmo_Prom', 'ESTRATO', 'Suelo', 'N_Mpio', 'C_DensUrba'])
med = med.set_geometry(shapely.force_2d(med.geometry.values))  # la capa trae Z y M basura
xy = shapely.get_coordinates(med.geometry.values)
med['X'], med['Y'] = xy[:, 0], xy[:, 1]
log("medidores: %d" % len(med))


coord = med.groupby(['X', 'Y'], sort=False).size().reset_index(name='n_medidores')
puntos = shapely.points(coord.X.values, coord.Y.values)
log("coordenadas unicas: %d (%.1f %% del total)" % (len(coord), 100 * len(coord) / len(med)))

# ------------------------------------------- distancia a las manzanas vecinas
# Se buscan todas las manzanas a UMBRAL+AMBIGUO metros para conocer, ademas de
# la mas cercana, la segunda: si estan casi a la misma distancia el punto esta
# sobre el eje de la via y la asignacion es un volado.
arbol = shapely.STRtree(manz.geometry.values)
i_pt, i_mz = arbol.query(puntos, predicate='dwithin', distance=UMBRAL + AMBIGUO)
dist = shapely.distance(puntos[i_pt], manz.geometry.values[i_mz])
log("parejas punto-manzana evaluadas: %d" % len(i_pt))

pares = (pd.DataFrame({'pt': i_pt, 'mz': i_mz, 'd': dist})
           .sort_values(['pt', 'd'], kind='stable'))
primera = pares.drop_duplicates('pt', keep='first')
resto = pares.drop(primera.index)
segunda = resto.drop_duplicates('pt', keep='first')

coord['manz_i'] = -1
coord['dist_m'] = np.nan
coord.loc[primera.pt.values, 'manz_i'] = primera.mz.values
coord.loc[primera.pt.values, 'dist_m'] = primera.d.values

dif_2da = pd.Series(np.nan, index=coord.index)
d_primera = pd.Series(primera.d.values, index=primera.pt.values)
dif_2da.loc[segunda.pt.values] = segunda.d.values - d_primera.reindex(segunda.pt.values).values

coord['metodo'] = np.where(coord.dist_m == 0, 'dentro',
                  np.where(coord.dist_m <= UMBRAL, 'cercano', 'no_asignado'))
coord.loc[coord.metodo == 'no_asignado', 'manz_i'] = -1
coord['ambiguo'] = ((coord.metodo == 'cercano') & (dif_2da <= AMBIGUO)).astype('int8')
coord['cod_manzana'] = np.where(coord.manz_i >= 0,
                                manz.COD_DANE_A.values[coord.manz_i.clip(lower=0)], '')
log("coordenadas -> dentro: %d | cercano: %d | sin asignar: %d" % (
    (coord.metodo == 'dentro').sum(), (coord.metodo == 'cercano').sum(),
    (coord.metodo == 'no_asignado').sum()))

# ------------------------------------------------ se devuelve a cada medidor
med = med.merge(coord[['X', 'Y', 'cod_manzana', 'dist_m', 'metodo', 'ambiguo']],
                on=['X', 'Y'], how='left')
total = len(med)
print("\n=== COBERTURA (%d medidores) ===" % total)
cob = med.metodo.value_counts().rename('medidores').to_frame()
cob['pct'] = (100 * cob.medidores / total).round(2)
print(cob.to_string())
print("asignados: %d (%.2f %%) | ambiguos: %d (%.2f %%)" % (
    (med.metodo != 'no_asignado').sum(), 100 * (med.metodo != 'no_asignado').mean(),
    med.ambiguo.sum(), 100 * med.ambiguo.mean()))

print("\n=== POR MUNICIPIO ===")
mun = med.assign(es_dentro=med.metodo.eq('dentro'),
                 es_cercano=med.metodo.eq('cercano'),
                 es_sin=med.metodo.eq('no_asignado')).groupby('N_Mpio').agg(
    medidores=('metodo', 'size'), dentro=('es_dentro', 'sum'),
    cercano=('es_cercano', 'sum'), sin_asignar=('es_sin', 'sum'),
    ambiguos=('ambiguo', 'sum'))
mun['pct_asignado'] = (100 * (mun.medidores - mun.sin_asignar) / mun.medidores).round(1)
print(mun.sort_values('medidores', ascending=False).to_string())
print("\nsin asignar por tipo de suelo:")
print(med.loc[med.metodo == 'no_asignado', 'Suelo'].value_counts().to_string())

# ------------------------------------------------------ agregado por manzana
asig = med[med.cod_manzana != ''].copy()
res = asig[asig.Categoria == 'RESIDENCIAL'].copy()
res['consumo'] = res.Csmo_Prom.replace(0, np.nan)  # el 0 es dato censurado, no consumo cero
g = pd.DataFrame({
    'medidores':       asig.groupby('cod_manzana').size(),
    'med_residencial': res.groupby('cod_manzana').size(),
    'med_comercial':   asig[asig.Categoria == 'COMERCIAL'].groupby('cod_manzana').size(),
    'med_industrial':  asig[asig.Categoria == 'INDUSTRIAL'].groupby('cod_manzana').size(),
    'med_dentro':      asig[asig.metodo == 'dentro'].groupby('cod_manzana').size(),
    'med_cercano':     asig[asig.metodo == 'cercano'].groupby('cod_manzana').size(),
    'med_ambiguo':     asig.groupby('cod_manzana').ambiguo.sum(),
    'consumo_prom':    res.groupby('cod_manzana').consumo.mean().round(1),
    'consumo_mediana': res.groupby('cod_manzana').consumo.median().round(1),
    'estrato_moda':    res.groupby('cod_manzana').ESTRATO.agg(
                          lambda s: s.mode().iat[0] if len(s.mode()) else np.nan),
})
for e in range(1, 7):
    g['med_estrato%d' % e] = res[res.ESTRATO == e].groupby('cod_manzana').size()

out = manz.merge(g, left_on='COD_DANE_A', right_index=True, how='left')
for c in [c for c in g.columns if c.startswith('med')]:
    out[c] = out[c].fillna(0)
out['med_x_vivienda'] = np.where(out.TVIVIENDA > 0, (out.medidores / out.TVIVIENDA).round(2), np.nan)
out['med_x_ha'] = (out.medidores / out.area_ha).round(1)

# --------------------------------------------------------------- validacion
print("\n=== VALIDACION CONTRA EL CENSO (residenciales vs TVIVIENDA) ===")
v = out[out.TVIVIENDA > 0]
for etiqueta, col in [('solo dentro', 'med_dentro'),
                      ('dentro + cercano<=%.1f m' % UMBRAL, 'medidores')]:
    r = np.corrcoef(v[col], v.TVIVIENDA)[0, 1]
    print("  %-26s manzanas con medidores: %5d/%5d | r=%.3f | mediana med/vivienda: %.2f" % (
        etiqueta, (v[col] > 0).sum(), len(v), r, (v[col] / v.TVIVIENDA).median()))
print("manzanas con al menos un medidor: %d de %d (%.1f %%)" % (
    (out.medidores > 0).sum(), len(out), 100 * (out.medidores > 0).mean()))
print("manzanas con razon medidores/vivienda fuera de 0,5-2,0 (revisar): %d" % (
    ((out.med_x_vivienda < 0.5) | (out.med_x_vivienda > 2)).sum()))

# ----------------------------------------------------------------- escritura
gpkg = SALIDA + '/manzanas_medidores.gpkg'
out.to_file(gpkg, layer='manzanas_medidores', driver='GPKG')
med.to_file(gpkg, layer='medidores_asignados', driver='GPKG')
out.drop(columns='geometry').to_csv(SALIDA + '/manzanas_amva_medidores.csv', index=False)
med.drop(columns='geometry').to_csv(SALIDA + '/medidores_asignados.csv', index=False)
log("archivos escritos en " + SALIDA)
