"""
Detección de anomalías (T8): señal complementaria al Score IMPERATOR.

Capa separada de `backend/procesador.py`: recibe el DataFrame ya procesado
(o crudo) y devuelve, por cliente y por transacción, un puntaje de anomalía no
supervisado, su percentil dentro del lote (0-100), un nivel (Alto/Medio/Bajo)
y una explicación con las variables que más alejan al cliente de la cartera.
No modifica el Score IMPERATOR, los niveles de riesgo ni el estado de los casos.

Modelo
------
Ensamble de dos puntajes no supervisados, combinados por el promedio de sus
percentiles dentro del lote (rank averaging, práctica estándar en detección de
outliers para mezclar detectores con escalas distintas):
* Isolation Forest (Liu, Ting y Zhou, 2008) implementado con numpy, sin sklearn:
  `requirements.txt` no incluye scikit-learn y añadirlo aumentaría la imagen en
  más de 100 MB (scipy + sklearn) y el tiempo de build; PyPI no está disponible
  en los entornos de prueba. La implementación propia usa las mismas fórmulas
  (subsample psi=256, límite de altura ceil(log2 psi), c(n) para normalizar y
  s = 2^(-E[h]/c(psi))) y es reproducible con semilla fija. Captura combinaciones
  raras de variables (interacciones).
* Puntaje robusto MAD multivariable: media de |x - mediana| / (1.4826 * MAD) por
  variable, recortada en 10. Captura la magnitud de la desviación simultánea en
  varias variables y es la misma medida que sustenta la explicación.
  En pruebas con anomalías inyectadas (fraccionamiento nocturno en efectivo) el
  ensamble mejora la precisión en el top-k frente a cada detector por separado.
* Con menos de MIN_CLIENTES_IF clientes el bosque no es estadísticamente
  significativo y se usa solo el puntaje MAD (fallback probado).

Explicabilidad
--------------
Para cada cliente se calcula la desviación robusta de cada variable frente a la
población (mediana y MAD del lote). Las tres de mayor magnitud se presentan con
valor, referencia y dirección en lenguaje claro. Es una explicación local
independiente del modelo: describe por qué el cliente es atípico respecto de la
cartera, que es lo que el Oficial de Cumplimiento necesita fundamentar.

Gobierno del modelo (ver docs/planes/INFORME_FASE2_2026-09.md, sección T8)
-----------------------------------------------------------------------------
* `VERSION_MODELO` y los parámetros usados viajan en `metadata` y en los reportes.
* Limitaciones: no supervisado (sin etiquetas), sensible al tamaño del lote,
  deriva entre períodos y sin memoria histórica: percentiles relativos al lote.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

VERSION_MODELO = "anomalias-if-mad-numpy/1.0.0"
METODO_ISOLATION_FOREST = "isolation_forest_numpy"
METODO_MAD = "mad_multivariable"
METODO_ENSAMBLE = "ensamble_if_mad"
MIN_CLIENTES_IF = 12
MIN_TRANSACCIONES_IF = 12
NIVEL_ALTO, NIVEL_MEDIO, NIVEL_BAJO = "Alto", "Medio", "Bajo"
UMBRAL_RTE = 10_000  # Art. 31 Ley 6593 (USD 10,000 o equivalente)
_ESCALA_MAD = 1.4826
_EULER = 0.5772156649015329
_PROXIMIDAD_UMBRAL = 0.80  # una operación está "cerca" de un umbral si monto en [0.8*U, U)
_MULTIPLO_REDONDO = 1_000
_HORA_INICIO, _HORA_FIN = 8, 18
_MAX_CLIENTES_TEXTO = 200

COLUMNAS_CASOS = ("Anomalia_Percentil", "Anomalia_Nivel")
COLUMNAS_TX = ("Anomalia_Tx_Score", "Anomalia_Tx_Percentil")

# Etiquetas legibles y formato de cada variable (para el Oficial de Cumplimiento).
DESCRIPCION_VARIABLES: Dict[str, Tuple[str, str]] = {
    "monto_max": ("Monto máximo de una operación", "moneda"),
    "monto_mediana": ("Monto típico (mediana) del cliente", "moneda"),
    "cv_monto": ("Variabilidad de los montos (coeficiente de variación)", "decimal"),
    "desv_perfil_max": ("Mayor desviación de una operación frente al perfil declarado", "veces"),
    "ratio_total_perfil": ("Total del período frente al perfil declarado", "veces"),
    "transacciones": ("Número de operaciones en el período", "entero"),
    "dias_activos": ("Días distintos con operaciones", "entero"),
    "tx_dia_max": ("Máximo de operaciones en un mismo día", "entero"),
    "prop_redondos": ("Proporción de montos redondos (múltiplos de 1,000)", "porcentaje"),
    "prop_cerca_umbral": ("Proporción de operaciones justo por debajo de un umbral (RTE, absoluto, FEIC)", "porcentaje"),
    "prop_fin_semana": ("Proporción de operaciones en fin de semana", "porcentaje"),
    "prop_hora_atipica": ("Proporción de operaciones fuera del horario 08:00-18:00", "porcentaje"),
    "prop_ubicacion_riesgo": ("Proporción de operaciones en ubicaciones de riesgo", "porcentaje"),
    "prop_efectivo": ("Proporción de operaciones en efectivo", "porcentaje"),
    "contrapartes_unicas": ("Número de contrapartes distintas", "entero"),
    "ratio_contrapartes": ("Contrapartes distintas por operación", "decimal"),
    "concentracion_contraparte": ("Concentración en la contraparte principal", "porcentaje"),
    # Variables por transacción
    "monto": ("Monto de la operación", "moneda"),
    "log_monto": ("Escala logarítmica del monto", "decimal"),
    "desv_perfil": ("Desviación frente al perfil declarado", "veces"),
    "monto_rel_cliente": ("Monto frente al monto típico del propio cliente", "veces"),
    "monto_redondo": ("Monto redondo (múltiplo de 1,000)", "indicador"),
    "cerca_umbral": ("Justo por debajo de un umbral (RTE, absoluto, FEIC)", "indicador"),
    "fin_semana": ("Operación en fin de semana", "indicador"),
    "hora_atipica": ("Operación fuera del horario 08:00-18:00", "indicador"),
    "ubicacion_riesgo": ("Ubicación de riesgo", "indicador"),
    "es_efectivo": ("Operación en efectivo", "indicador"),
}


class ErrorAnomalias(ValueError):
    """Entrada inválida para el cálculo de anomalías."""


@dataclass(frozen=True)
class ParametrosAnomalia:
    activa: bool = True
    n_arboles: int = 100
    tamano_muestra: int = 256
    semilla: int = 42
    percentil_alto: int = 90
    percentil_medio: int = 75
    score_punto_ciego: float = 3.0
    top_variables: int = 3

    @classmethod
    def desde_config(cls, cfg: Optional[dict]) -> "ParametrosAnomalia":
        cfg = cfg or {}
        base = cls()
        return cls(
            activa=bool(cfg.get("anomalia_activa", base.activa)),
            n_arboles=int(cfg.get("anomalia_n_arboles", base.n_arboles)),
            tamano_muestra=base.tamano_muestra,
            semilla=int(cfg.get("anomalia_semilla", base.semilla)),
            percentil_alto=int(cfg.get("anomalia_percentil_alto", base.percentil_alto)),
            percentil_medio=int(cfg.get("anomalia_percentil_medio", base.percentil_medio)),
            score_punto_ciego=float(cfg.get("anomalia_score_punto_ciego", base.score_punto_ciego)),
            top_variables=base.top_variables,
        )

    def validar(self) -> None:
        if self.n_arboles < 1 or self.n_arboles > 1000:
            raise ErrorAnomalias("n_arboles debe estar entre 1 y 1000.")
        if self.tamano_muestra < 4:
            raise ErrorAnomalias("tamano_muestra debe ser al menos 4.")
        if not (0 <= self.percentil_medio < self.percentil_alto <= 100):
            raise ErrorAnomalias("Se requiere 0 <= percentil_medio < percentil_alto <= 100.")
        if self.semilla < 0:
            raise ErrorAnomalias("La semilla debe ser un entero no negativo.")

    def hash(self) -> str:
        """Huella de los parámetros y la versión del modelo (clave de caché y trazabilidad)."""
        base = json.dumps({"version": VERSION_MODELO, **asdict(self)}, sort_keys=True)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


@dataclass
class ResultadoAnomalias:
    clientes: pd.DataFrame
    transacciones: pd.DataFrame
    variables_cliente: pd.DataFrame
    metadata: dict = field(default_factory=dict)

    @property
    def vacio(self) -> bool:
        return self.clientes.empty


# ── Isolation Forest con numpy ─────────────────────────────────────────────

def _c(n) -> np.ndarray:
    """Longitud media de camino de un BST fallido con n nodos (normalización)."""
    n = np.asarray(n, dtype=float)
    out = np.zeros_like(n)
    mayor = n > 2
    out[mayor] = 2.0 * (np.log(n[mayor] - 1.0) + _EULER) - 2.0 * (n[mayor] - 1.0) / n[mayor]
    out[n == 2] = 1.0
    return out


class _Arbol:
    """Árbol de aislamiento almacenado en arreglos (evaluación vectorizada)."""
    __slots__ = ("variable", "corte", "izq", "der", "tamano")

    def __init__(self):
        self.variable: List[int] = []
        self.corte: List[float] = []
        self.izq: List[int] = []
        self.der: List[int] = []
        self.tamano: List[int] = []

    def _nuevo(self, variable, corte, tamano) -> int:
        self.variable.append(variable)
        self.corte.append(corte)
        self.izq.append(-1)
        self.der.append(-1)
        self.tamano.append(tamano)
        return len(self.variable) - 1

    def construir(self, X: np.ndarray, rng: np.random.Generator, limite: int) -> None:
        pendientes: List[Tuple[int, np.ndarray, int]] = []
        raiz = self._nuevo(-1, 0.0, len(X))
        pendientes.append((raiz, np.arange(len(X)), 0))
        while pendientes:
            nodo, filas, prof = pendientes.pop()
            if prof >= limite or len(filas) <= 1:
                continue
            sub = X[filas]
            minimos, maximos = sub.min(axis=0), sub.max(axis=0)
            candidatas = np.flatnonzero(maximos > minimos)
            if candidatas.size == 0:
                continue
            j = int(rng.choice(candidatas))
            corte = float(rng.uniform(minimos[j], maximos[j]))
            mascara = sub[:, j] < corte
            if not mascara.any() or mascara.all():
                continue
            self.variable[nodo] = j
            self.corte[nodo] = corte
            self.izq[nodo] = self._nuevo(-1, 0.0, int(mascara.sum()))
            self.der[nodo] = self._nuevo(-1, 0.0, int((~mascara).sum()))
            pendientes.append((self.izq[nodo], filas[mascara], prof + 1))
            pendientes.append((self.der[nodo], filas[~mascara], prof + 1))

    def finalizar(self) -> None:
        self.variable = np.asarray(self.variable, dtype=int)
        self.corte = np.asarray(self.corte, dtype=float)
        self.izq = np.asarray(self.izq, dtype=int)
        self.der = np.asarray(self.der, dtype=int)
        self.tamano = np.asarray(self.tamano, dtype=int)

    def longitud_camino(self, X: np.ndarray, limite: int) -> np.ndarray:
        nodo = np.zeros(len(X), dtype=int)
        prof = np.zeros(len(X), dtype=float)
        for _ in range(limite + 1):
            interno = self.variable[nodo] >= 0
            if not interno.any():
                break
            idx = np.flatnonzero(interno)
            n_idx = nodo[idx]
            va_izq = X[idx, self.variable[n_idx]] < self.corte[n_idx]
            nodo[idx] = np.where(va_izq, self.izq[n_idx], self.der[n_idx])
            prof[idx] += 1.0
        return prof + _c(self.tamano[nodo])


class BosqueAislamiento:
    """Isolation Forest reproducible (numpy). fit(X) y puntuar(X) en [0, 1]."""

    def __init__(self, n_arboles: int = 100, tamano_muestra: int = 256, semilla: int = 42):
        self.n_arboles = int(n_arboles)
        self.tamano_muestra = int(tamano_muestra)
        self.semilla = int(semilla)
        self.arboles: List[_Arbol] = []
        self.psi = 0
        self.limite = 0

    def fit(self, X: np.ndarray) -> "BosqueAislamiento":
        X = np.asarray(X, dtype=float)
        if X.ndim != 2 or X.shape[0] < 2:
            raise ErrorAnomalias("Se requieren al menos 2 observaciones para ajustar el bosque.")
        rng = np.random.default_rng(self.semilla)
        self.psi = min(self.tamano_muestra, X.shape[0])
        self.limite = int(math.ceil(math.log2(max(self.psi, 2))))
        self.arboles = []
        for _ in range(self.n_arboles):
            muestra = rng.choice(X.shape[0], size=self.psi, replace=False)
            arbol = _Arbol()
            arbol.construir(X[muestra], rng, self.limite)
            arbol.finalizar()
            self.arboles.append(arbol)
        return self

    def longitud_media(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        acumulado = np.zeros(len(X), dtype=float)
        for arbol in self.arboles:
            acumulado += arbol.longitud_camino(X, self.limite)
        return acumulado / max(len(self.arboles), 1)

    def puntuar(self, X: np.ndarray) -> np.ndarray:
        """Puntaje de anomalía s(x) = 2^(-E[h(x)] / c(psi)); cercano a 1 = anómalo."""
        norm = float(_c(np.array([self.psi]))[0]) or 1.0
        return np.power(2.0, -self.longitud_media(X) / norm)


# ── Ingeniería de variables ────────────────────────────────────────────────

def _numerica(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").astype(float)


def _booleana(serie: pd.Series) -> pd.Series:
    if serie.dtype == bool:
        return serie.astype(float)
    texto = serie.astype(str).str.strip().str.lower()
    return texto.isin(["si", "sí", "s", "yes", "y", "true", "1", "x"]).astype(float)


def _umbrales(cfg: Optional[dict]) -> List[float]:
    cfg = cfg or {}
    valores = [UMBRAL_RTE, cfg.get("umbral_absoluto"), cfg.get("umbral_feic")]
    limpios = []
    for v in valores:
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v > 0 and v not in limpios:
            limpios.append(v)
    return limpios


def variables_transaccion(df: pd.DataFrame, cfg: Optional[dict] = None) -> pd.DataFrame:
    """Variables numéricas por transacción (índice alineado con df). Tolera columnas ausentes y nulos."""
    if "Monto" not in df.columns or "Cliente" not in df.columns:
        raise ErrorAnomalias("Se requieren las columnas 'Cliente' y 'Monto'.")
    monto = _numerica(df["Monto"]).fillna(0.0).clip(lower=0.0)
    out = pd.DataFrame(index=df.index)
    out["monto"] = monto
    out["log_monto"] = np.log1p(monto)
    if "Perfil" in df.columns:
        perfil = _numerica(df["Perfil"])
        perfil = perfil.where(perfil > 0)
        out["desv_perfil"] = ((monto - perfil) / perfil).fillna(0.0)
    else:
        out["desv_perfil"] = 0.0
    cliente = df["Cliente"].astype(str)
    mediana_cliente = monto.groupby(cliente).transform("median").replace(0, np.nan)
    out["monto_rel_cliente"] = (monto / mediana_cliente).fillna(1.0)
    out["monto_redondo"] = ((monto > 0) & (np.mod(monto, _MULTIPLO_REDONDO) == 0)).astype(float)
    cerca = pd.Series(False, index=df.index)
    for u in _umbrales(cfg):
        cerca = cerca | ((monto >= _PROXIMIDAD_UMBRAL * u) & (monto < u))
    out["cerca_umbral"] = cerca.astype(float)
    if "Fecha" in df.columns:
        fecha = pd.to_datetime(df["Fecha"], errors="coerce")
        out["fin_semana"] = (fecha.dt.dayofweek >= 5).fillna(False).astype(float)
        hora = fecha.dt.hour
        con_hora = fecha.notna() & ((hora != 0) | (fecha.dt.minute != 0)).fillna(False)
        if bool(con_hora.any()):
            atipica = ((hora < _HORA_INICIO) | (hora >= _HORA_FIN)) & con_hora
            out["hora_atipica"] = atipica.fillna(False).astype(float)
    if "Ubicacion_Riesgo" in df.columns:
        out["ubicacion_riesgo"] = _booleana(df["Ubicacion_Riesgo"])
    elif "UbicacionRiesgo" in df.columns:
        out["ubicacion_riesgo"] = _booleana(df["UbicacionRiesgo"])
    for col in ("Tipo_Instrumento", "TipoOperacion"):
        if col in df.columns:
            out["es_efectivo"] = df[col].astype(str).str.lower().str.contains("efectivo", na=False).astype(float)
            break
    return out


def variables_cliente(df: pd.DataFrame, cfg: Optional[dict] = None,
                      tx: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Variables por cliente (una fila por cliente, índice = Cliente)."""
    if tx is None:
        tx = variables_transaccion(df, cfg)
    cliente = df["Cliente"].astype(str)
    g = tx.groupby(cliente)
    out = pd.DataFrame(index=g.size().index)
    out.index.name = "Cliente"
    out["monto_max"] = g["monto"].max()
    out["monto_mediana"] = g["monto"].median()
    media = g["monto"].mean()
    out["cv_monto"] = (g["monto"].std(ddof=0) / media.replace(0, np.nan)).fillna(0.0)
    out["desv_perfil_max"] = g["desv_perfil"].max()
    if "Perfil" in df.columns:
        perfil = _numerica(df["Perfil"]).groupby(cliente).first()
        total = g["monto"].sum()
        out["ratio_total_perfil"] = (total / perfil.where(perfil > 0)).fillna(0.0)
    out["transacciones"] = g.size().astype(float)
    if "Fecha" in df.columns:
        fecha = pd.to_datetime(df["Fecha"], errors="coerce")
        dia = fecha.dt.normalize()
        por_dia = pd.DataFrame({"c": cliente, "d": dia}).dropna().groupby(["c", "d"]).size()
        if not por_dia.empty:
            out["dias_activos"] = por_dia.groupby(level=0).size().reindex(out.index).fillna(0.0).astype(float)
            out["tx_dia_max"] = por_dia.groupby(level=0).max().reindex(out.index).fillna(0.0).astype(float)
    proporciones = {
        "prop_redondos": "monto_redondo", "prop_cerca_umbral": "cerca_umbral",
        "prop_fin_semana": "fin_semana", "prop_hora_atipica": "hora_atipica",
        "prop_ubicacion_riesgo": "ubicacion_riesgo", "prop_efectivo": "es_efectivo",
    }
    for destino, origen in proporciones.items():
        if origen in tx.columns:
            out[destino] = g[origen].mean()
    if "Cliente_Destino" in df.columns:
        destino = df["Cliente_Destino"].astype(str).str.strip()
        destino = destino.where(destino.ne("") & destino.str.lower().ne("nan"))
        pares = pd.DataFrame({"c": cliente, "d": destino}).dropna()
        if not pares.empty:
            unicas = pares.groupby("c")["d"].nunique().reindex(out.index).fillna(0.0)
            out["contrapartes_unicas"] = unicas.astype(float)
            out["ratio_contrapartes"] = (unicas / out["transacciones"]).fillna(0.0)
            conteo = pares.groupby(["c", "d"]).size()
            maximo = conteo.groupby(level=0).max().reindex(out.index)
            total_pares = pares.groupby("c").size().reindex(out.index)
            out["concentracion_contraparte"] = (maximo / total_pares).fillna(0.0)
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)


# ── Puntajes y explicaciones ───────────────────────────────────────────────

def _columnas_utiles(X: pd.DataFrame) -> List[str]:
    return [c for c in X.columns if X[c].nunique(dropna=True) > 1]


def _desviaciones_robustas(X: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """z robusta por variable: (x - mediana) / (1.4826 * MAD); si MAD = 0 usa IQR/1.349 o std."""
    mediana = X.median()
    mad = (X - mediana).abs().median() * _ESCALA_MAD
    iqr = (X.quantile(0.75) - X.quantile(0.25)) / 1.349
    std = X.std(ddof=0)
    escala = mad.where(mad > 0, iqr.where(iqr > 0, std))
    escala = escala.where(escala > 0, np.nan)
    z = ((X - mediana) / escala).fillna(0.0)
    return z, mediana, escala


def _percentiles(puntaje: np.ndarray) -> np.ndarray:
    n = len(puntaje)
    if n == 0:
        return np.array([], dtype=float)
    rangos = pd.Series(puntaje).rank(method="average", ascending=True).to_numpy()
    return np.round(rangos / n * 100.0, 1)


def _niveles(percentil: np.ndarray, params: ParametrosAnomalia) -> List[str]:
    return [NIVEL_ALTO if p >= params.percentil_alto else NIVEL_MEDIO if p >= params.percentil_medio else NIVEL_BAJO
            for p in percentil]


def _puntaje_mad(X: pd.DataFrame) -> np.ndarray:
    z, _m, _e = _desviaciones_robustas(X)
    return z.abs().clip(upper=10.0).mean(axis=1).to_numpy() / 10.0


def _puntuar(X: pd.DataFrame, params: ParametrosAnomalia, minimo_if: int) -> Tuple[np.ndarray, str, List[str]]:
    """Devuelve (puntaje en [0,1], método, columnas usadas). Ensamble IF + MAD por promedio de percentiles."""
    columnas = _columnas_utiles(X)
    n = len(X)
    if n == 0:
        return np.array([], dtype=float), METODO_MAD, columnas
    if not columnas:
        return np.zeros(n), METODO_MAD, columnas
    puntaje_mad = _puntaje_mad(X[columnas])
    if n < minimo_if:
        return puntaje_mad, METODO_MAD, columnas
    matriz = X[columnas].to_numpy()
    puntaje_if = BosqueAislamiento(params.n_arboles, params.tamano_muestra, params.semilla).fit(matriz).puntuar(matriz)
    ensamble = (_percentiles(puntaje_if) + _percentiles(puntaje_mad)) / 200.0
    return ensamble, METODO_ENSAMBLE, columnas


def formatear_valor(valor: float, formato: str, moneda: str = "Q") -> str:
    if formato == "moneda":
        return f"{moneda}{valor:,.0f}"
    if formato == "porcentaje":
        return f"{valor * 100:.0f}%"
    if formato == "veces":
        return f"{valor:.2f} veces"
    if formato == "entero":
        return f"{valor:.0f}"
    if formato == "indicador":
        return "sí" if valor >= 0.5 else "no"
    return f"{valor:.2f}"


def explicar(X: pd.DataFrame, top: int = 3, moneda: str = "Q") -> Dict[str, List[dict]]:
    """Top variables por fila: [{variable, etiqueta, valor, referencia, z, direccion, texto}]."""
    columnas = _columnas_utiles(X)
    if not columnas or X.empty:
        return {str(i): [] for i in X.index}
    z, mediana, _escala = _desviaciones_robustas(X[columnas])
    z_abs = z.abs().to_numpy()
    valores = X[columnas].to_numpy()
    salida: Dict[str, List[dict]] = {}
    for fila, idx in enumerate(X.index):
        orden = np.argsort(-z_abs[fila], kind="stable")[:top]
        items = []
        for j in orden:
            if z_abs[fila, j] <= 0:
                continue
            col = columnas[j]
            etiqueta, formato = DESCRIPCION_VARIABLES.get(col, (col, "decimal"))
            direccion = "por encima" if valores[fila, j] > mediana[col] else "por debajo"
            valor_txt = formatear_valor(float(valores[fila, j]), formato, moneda)
            ref_txt = formatear_valor(float(mediana[col]), formato, moneda)
            zj = float(z.iloc[fila, j])
            texto = (f"{etiqueta}: {valor_txt}, {direccion} de la cartera (mediana {ref_txt}; "
                     f"{abs(zj):.1f} desviaciones robustas).")
            items.append({"variable": col, "etiqueta": etiqueta, "valor": float(valores[fila, j]),
                          "referencia": float(mediana[col]), "z": zj, "direccion": direccion, "texto": texto})
        salida[str(idx)] = items
    return salida


def _resultado_vacio(motivo: str, params: ParametrosAnomalia) -> ResultadoAnomalias:
    clientes = pd.DataFrame(columns=["Cliente", "Anomalia_Score", "Anomalia_Percentil", "Anomalia_Nivel",
                                     "Anomalia_Explicacion", "Anomalia_Variables"])
    tx = pd.DataFrame(columns=list(COLUMNAS_TX))
    return ResultadoAnomalias(clientes, tx, pd.DataFrame(), metadata={
        "version_modelo": VERSION_MODELO, "metodo_clientes": None, "metodo_transacciones": None,
        "parametros": asdict(params), "hash_parametros": params.hash(), "n_clientes": 0,
        "n_transacciones": 0, "variables_cliente": [], "variables_transaccion": [], "motivo": motivo,
        "duracion_s": 0.0,
    })


def calcular_anomalias(df: pd.DataFrame, cfg: Optional[dict] = None, hash_lote: Optional[str] = None,
                       params: Optional[ParametrosAnomalia] = None, moneda: Optional[str] = None) -> ResultadoAnomalias:
    """
    Calcula la señal de anomalía por cliente y por transacción.
    No modifica `df`. Devuelve un ResultadoAnomalias con metadata de trazabilidad.
    """
    inicio = time.perf_counter()
    params = params or ParametrosAnomalia.desde_config(cfg)
    params.validar()
    moneda = moneda or ("USD " if (cfg or {}).get("moneda") == "USD" else "Q")
    if not params.activa:
        return _resultado_vacio("La señal de anomalía está desactivada en la configuración.", params)
    if df is None or len(df) == 0:
        return _resultado_vacio("Sin transacciones.", params)
    if "Cliente" not in df.columns or "Monto" not in df.columns:
        return _resultado_vacio("Faltan las columnas 'Cliente' y/o 'Monto'.", params)

    tx = variables_transaccion(df, cfg)
    X_cli = variables_cliente(df, cfg, tx)

    puntaje_cli, metodo_cli, cols_cli = _puntuar(X_cli, params, MIN_CLIENTES_IF)
    percentil_cli = _percentiles(puntaje_cli)
    explicaciones = explicar(X_cli, params.top_variables, moneda)
    clientes = pd.DataFrame({
        "Cliente": X_cli.index.astype(str),
        "Anomalia_Score": np.round(puntaje_cli, 4),
        "Anomalia_Percentil": percentil_cli,
        "Anomalia_Nivel": _niveles(percentil_cli, params),
    })
    clientes["Anomalia_Variables"] = [explicaciones.get(c, []) for c in clientes["Cliente"]]
    clientes["Anomalia_Explicacion"] = [" ".join(i["texto"] for i in v) or "Sin variables discriminantes."
                                        for v in clientes["Anomalia_Variables"]]
    clientes = clientes.sort_values(["Anomalia_Percentil", "Cliente"], ascending=[False, True]).reset_index(drop=True)

    tx_num = tx.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    puntaje_tx, metodo_tx, cols_tx = _puntuar(tx_num, params, MIN_TRANSACCIONES_IF)
    transacciones = pd.DataFrame({
        "Anomalia_Tx_Score": np.round(puntaje_tx, 4),
        "Anomalia_Tx_Percentil": _percentiles(puntaje_tx),
    }, index=df.index)

    metadata = {
        "version_modelo": VERSION_MODELO,
        "metodo_clientes": metodo_cli,
        "metodo_transacciones": metodo_tx,
        "parametros": asdict(params),
        "hash_parametros": params.hash(),
        "hash_lote": hash_lote,
        "n_clientes": int(len(clientes)),
        "n_transacciones": int(len(df)),
        "variables_cliente": cols_cli,
        "variables_transaccion": cols_tx,
        "motivo": None,
        "duracion_s": round(time.perf_counter() - inicio, 3),
    }
    return ResultadoAnomalias(clientes, transacciones, X_cli, metadata)


# ── Integración con el DataFrame de casos ───────────────────────────────────

def asegurar_columnas(casos: pd.DataFrame) -> None:
    if "Anomalia_Percentil" not in casos.columns:
        casos["Anomalia_Percentil"] = np.nan
    if "Anomalia_Nivel" not in casos.columns:
        casos["Anomalia_Nivel"] = "N/D"


def marcar_casos(casos: pd.DataFrame, resultado: Optional[ResultadoAnomalias]) -> int:
    """Añade in situ Anomalia_Percentil y Anomalia_Nivel a `casos`. No toca Score ni Nivel_Riesgo."""
    asegurar_columnas(casos)
    if resultado is None or resultado.vacio or "Cliente" not in casos.columns:
        return 0
    por_cliente = resultado.clientes.set_index("Cliente")
    clave = casos["Cliente"].astype(str)
    percentil = clave.map(por_cliente["Anomalia_Percentil"])
    nivel = clave.map(por_cliente["Anomalia_Nivel"])
    casos["Anomalia_Percentil"] = percentil.to_numpy()
    casos["Anomalia_Nivel"] = nivel.fillna("N/D").to_numpy()
    return int(percentil.notna().sum())


def puntos_ciegos(casos: pd.DataFrame, params: Optional[ParametrosAnomalia] = None) -> pd.DataFrame:
    """Clientes con anomalía Alta y Score IMPERATOR bajo: posibles puntos ciegos de las reglas."""
    params = params or ParametrosAnomalia()
    if casos.empty or "Anomalia_Nivel" not in casos.columns or "Score_Max" not in casos.columns:
        return casos.iloc[0:0]
    mascara = (casos["Anomalia_Nivel"] == NIVEL_ALTO) & (casos["Score_Max"].astype(float) < params.score_punto_ciego)
    return casos[mascara].sort_values("Anomalia_Percentil", ascending=False)


def resumen_trazabilidad(metadata: dict) -> str:
    """Línea de trazabilidad para reportes: versión, método, parámetros y lote."""
    p = metadata.get("parametros", {})
    partes = [
        f"Modelo {metadata.get('version_modelo', VERSION_MODELO)}",
        f"método clientes: {metadata.get('metodo_clientes') or 'n/d'}",
        f"árboles: {p.get('n_arboles')}, muestra: {p.get('tamano_muestra')}, semilla: {p.get('semilla')}",
        f"percentiles alto/medio: {p.get('percentil_alto')}/{p.get('percentil_medio')}",
        f"parámetros: {metadata.get('hash_parametros')}",
    ]
    if metadata.get("hash_lote"):
        partes.append(f"lote: {str(metadata['hash_lote'])[:12]}")
    return " · ".join(partes)
