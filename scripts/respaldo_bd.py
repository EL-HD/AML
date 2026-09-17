#!/usr/bin/env python3
"""
Respaldo cifrado de la base de datos de Sovereign AML (T7).

    python scripts/respaldo_bd.py                 Respalda y aplica retención
    python scripts/respaldo_bd.py --sin-retencion Respalda sin borrar respaldos antiguos
    python scripts/respaldo_bd.py --solo-retencion [--simular]
    python scripts/respaldo_bd.py --listar        Inventario del almacén
    python scripts/respaldo_bd.py --generar-clave Imprime una BACKUP_ENCRYPTION_KEY nueva

Variables de entorno:
    DATABASE_URL (o DB_HOST/DB_PORT/DB_USER/DB_PASS/DB_NAME)  Origen del respaldo.
    BACKUP_ENCRYPTION_KEY   Clave maestra (formato Fernet). Obligatoria.
    BACKUP_DIR              Directorio local de destino (por defecto backups/).
    BACKUP_S3_BUCKET        Si se define, destino S3 compatible (requiere boto3);
                            opcionales BACKUP_S3_PREFIX, BACKUP_S3_ENDPOINT, BACKUP_S3_REGION
                            y las credenciales estándar AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
    BACKUP_RETENCION_DIARIOS / _SEMANALES / _MENSUALES   Por defecto 7 / 4 / 12.
    BACKUP_TMPDIR           Directorio temporal para el volcado en claro (por defecto el del sistema).

Sale con código 0 si el respaldo se almacenó; 1 ante cualquier error controlado.
La contraseña de la base nunca se imprime ni se pasa por la línea de comandos.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os  # noqa: E402

from backend import respaldos  # noqa: E402


def _argumentos(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Respaldo cifrado de la base de datos de Sovereign AML.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--solo-retencion", action="store_true", help="Solo aplica la política de retención.")
    grupo.add_argument("--listar", action="store_true", help="Lista los respaldos del almacén y su validez.")
    grupo.add_argument("--generar-clave", action="store_true", help="Genera una clave nueva y termina.")
    parser.add_argument("--sin-retencion", action="store_true", help="No borra respaldos antiguos tras respaldar.")
    parser.add_argument("--simular", action="store_true", help="Con --solo-retencion: muestra qué se borraría sin borrar.")
    parser.add_argument("--json", action="store_true", help="Imprime el resultado en JSON (para bitácoras del cron).")
    return parser.parse_args(argv)


def _imprimir_listado(respaldos_listados) -> None:
    if not respaldos_listados:
        print("No hay respaldos en el almacén.")
        return
    for r in sorted(respaldos_listados, key=lambda x: x.fecha, reverse=True):
        estado = "VALIDO" if r.valido else f"INVALIDO ({r.motivo})"
        print(f"{r.nombre}  {r.fecha.strftime('%Y-%m-%d %H:%M:%S UTC')}  {estado}")


def main(argv=None) -> int:
    args = _argumentos(argv)
    if args.generar_clave:
        print(respaldos.generar_clave_texto())
        return 0
    log = respaldos.configurar_logging()
    try:
        conexion = respaldos.conexion_desde_entorno()
        log = respaldos.configurar_logging(secretos=[conexion.password])
        almacen = respaldos.almacen_desde_entorno(directorio_defecto=str(ROOT / "backups"))
        if args.listar:
            _imprimir_listado(respaldos.inventariar(almacen))
            return 0
        politica = respaldos.PoliticaRetencion.desde_entorno()
        if args.solo_retencion:
            resultado = respaldos.aplicar_retencion(almacen, politica, simular=args.simular)
            print(json.dumps(resultado, indent=2, ensure_ascii=False))
            return 0
        clave = respaldos.clave_maestra_desde_texto(os.environ.get("BACKUP_ENCRYPTION_KEY"))
        resultado = respaldos.respaldar(conexion, clave, almacen, politica, aplicar_politica=not args.sin_retencion)
        manifiesto = resultado["manifiesto"]
        if args.json:
            print(json.dumps(resultado, indent=2, ensure_ascii=False))
        else:
            log.info("Manifiesto: %s (%s); última migración %s; anclas de auditoría: %s",
                     manifiesto["nombre"] + respaldos.SUFIJO_MANIFIESTO, manifiesto["fecha_utc"],
                     manifiesto["ultima_migracion"],
                     ", ".join(f"{a['licenciaid'][:8]}:{a['ultimo_seq']}:{a['ultimo_hash'][:12]}"
                               for a in manifiesto["anclas_auditoria"]) or "ninguna")
        return 0
    except respaldos.RespaldoError as exc:
        log.error("Respaldo fallido: %s", exc)
        return 1
    except OSError as exc:
        log.error("Error de sistema durante el respaldo: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
