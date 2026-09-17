"""
Medición de duplicación de código sin dependencias externas (alternativa a jscpd).

Método: se normalizan las líneas de código (sin espacios, comentarios ni líneas
vacías) y se buscan ventanas de N líneas consecutivas (por defecto 6) que se
repitan en cualquier archivo. El porcentaje es líneas duplicadas / líneas totales.

Uso: python scripts/medir_duplicacion.py [--ventana 6] [--umbral 10] rutas...
Sale con código 1 si la duplicación supera el umbral.
"""
import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path


def _lineas_codigo(ruta: Path):
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        texto = "".join(linea.split())
        if not texto or texto.startswith("#"):
            continue
        yield numero, texto


def medir(rutas, ventana: int):
    ventanas = defaultdict(list)
    lineas_por_archivo = {}
    for ruta in rutas:
        lineas = list(_lineas_codigo(ruta))
        lineas_por_archivo[ruta] = lineas
        for i in range(len(lineas) - ventana + 1):
            # sha256: la huella no es criptográfica pero evita la alerta B324 de bandit en CI
            clave = hashlib.sha256("\n".join(t for _, t in lineas[i:i + ventana]).encode()).hexdigest()
            ventanas[clave].append((ruta, i))
    duplicadas = defaultdict(set)
    for clave, apariciones in ventanas.items():
        if len(apariciones) < 2:
            continue
        for ruta, i in apariciones:
            duplicadas[ruta].update(range(i, i + ventana))
    total = sum(len(v) for v in lineas_por_archivo.values())
    dup = sum(len(v) for v in duplicadas.values())
    detalle = {r: len(v) for r, v in duplicadas.items()}
    return total, dup, detalle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rutas", nargs="*", default=["app.py", "auth_api.py", "backend", "frontend"])
    parser.add_argument("--ventana", type=int, default=6)
    parser.add_argument("--umbral", type=float, default=10.0)
    args = parser.parse_args()
    archivos = []
    for r in args.rutas:
        p = Path(r)
        archivos += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    total, dup, detalle = medir(archivos, args.ventana)
    porcentaje = (dup / total * 100) if total else 0.0
    for ruta, n in sorted(detalle.items(), key=lambda x: -x[1])[:10]:
        print(f"  {ruta}: {n} líneas en bloques repetidos")
    print(f"Líneas de código: {total} · duplicadas: {dup} · duplicación: {porcentaje:.2f}% (umbral {args.umbral}%)")
    return 1 if porcentaje > args.umbral else 0


if __name__ == "__main__":
    sys.exit(main())
