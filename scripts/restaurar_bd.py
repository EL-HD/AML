#!/usr/bin/env python3
"""
Restauración de un respaldo cifrado de Sovereign AML (T7).

    python scripts/restaurar_bd.py --respaldo respaldo_20260917T030000Z --destino postgresql://u:p@host/aml_prueba
    python scripts/restaurar_bd.py --respaldo <nombre> --destino <URL> --crear-base
    python scripts/restaurar_bd.py --respaldo <nombre> --verificar-solo
    python scripts/restaurar_bd.py --archivo backups/<nombre>.dump.enc --destino-local --limpiar
    python scripts/restaurar_bd.py --respaldo <nombre> --solo-descifrar /ruta/segura/volcado.dump

El respaldo se toma del almacén configurado (BACKUP_DIR o BACKUP_S3_BUCKET) o de un
archivo local con --archivo <ruta.dump.enc> (el manifiesto debe estar junto a él).

Protección de producción: si el destino coincide con DATABASE_URL o su host pertenece a
Railway (*.railway.internal, *.rlwy.net, *.railway.app) o a BACKUP_HOSTS_PRODUCCION, la
restauración se niega salvo que se pasen a la vez la bandera --confirmar-produccion y la
variable BACKUP_PERMITIR_RESTAURAR_PRODUCCION=si.

Flujo: verificar firma del manifiesto -> SHA-256 del archivo cifrado -> descifrar bloque a
bloque (autenticado) -> SHA-256 y tamaño del volcado -> pg_restore -> comparar migraciones.
Sale con 0 si todo se completó; 1 ante error controlado; 2 si se bloqueó por producción.
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import respaldos  # noqa: E402

VARIABLE_PRODUCCION = "BACKUP_PERMITIR_RESTAURAR_PRODUCCION"


def _argumentos(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restaura un respaldo cifrado de Sovereign AML.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--respaldo", help="Nombre del respaldo en el almacén (respaldo_AAAAMMDDTHHMMSSZ).")
    origen.add_argument("--archivo", help="Ruta local a un archivo .dump.enc (manifiesto junto a él).")
    accion = parser.add_mutually_exclusive_group(required=True)
    accion.add_argument("--destino", help="URL postgresql:// de la base destino (explícita, nunca implícita).")
    accion.add_argument("--destino-local", action="store_true",
                        help="Destino tomado de DB_HOST/DB_PORT/DB_USER/DB_PASS/DB_NAME (orquestador ./aml); "
                             "nunca de DATABASE_URL. Evita pasar la contraseña por la línea de comandos.")
    accion.add_argument("--verificar-solo", action="store_true", help="Verifica y descifra sin restaurar.")
    accion.add_argument("--solo-descifrar", metavar="RUTA", help="Escribe el volcado descifrado en RUTA (permisos 0600).")
    parser.add_argument("--crear-base", action="store_true", help="Crea la base destino si no existe.")
    parser.add_argument("--limpiar", action="store_true",
                        help="Pasa --clean --if-exists a pg_restore (sobrescribe objetos existentes).")
    parser.add_argument("--confirmar-produccion", action="store_true",
                        help=f"Primera de las dos confirmaciones para producción (la otra es {VARIABLE_PRODUCCION}=si).")
    return parser.parse_args(argv)


def _obtener_respaldo(args, tmp_dir: Path):
    """Devuelve (ruta_cifrado, manifiesto) desde el almacén o desde un archivo local."""
    if args.archivo:
        cifrado = respaldos.ruta_segura(args.archivo)
        if not cifrado.is_file() or not cifrado.name.endswith(respaldos.SUFIJO_CIFRADO):
            raise respaldos.RespaldoError(f"No existe el archivo cifrado o no termina en {respaldos.SUFIJO_CIFRADO}.")
        nombre = cifrado.name[: -len(respaldos.SUFIJO_CIFRADO)]
        manifiesto_ruta = cifrado.with_name(nombre + respaldos.SUFIJO_MANIFIESTO)
        if not manifiesto_ruta.is_file():
            raise respaldos.RespaldoError(f"Falta el manifiesto {manifiesto_ruta.name} junto al archivo cifrado.")
        return cifrado, respaldos.cargar_manifiesto(manifiesto_ruta.read_text(encoding="utf-8"))
    nombre = args.respaldo.strip()
    if not respaldos.PATRON_NOMBRE.match(nombre):
        raise respaldos.RespaldoError("Nombre de respaldo inválido; use respaldo_AAAAMMDDTHHMMSSZ.")
    almacen = respaldos.almacen_desde_entorno(directorio_defecto=str(ROOT / "backups"))
    manifiesto = respaldos.cargar_manifiesto(almacen.leer_texto(nombre + respaldos.SUFIJO_MANIFIESTO))
    cifrado = tmp_dir / (nombre + respaldos.SUFIJO_CIFRADO)
    almacen.descargar(nombre + respaldos.SUFIJO_CIFRADO, cifrado)
    return cifrado, manifiesto


def main(argv=None) -> int:
    args = _argumentos(argv)
    log = respaldos.configurar_logging()
    try:
        clave = respaldos.clave_maestra_desde_texto(os.environ.get("BACKUP_ENCRYPTION_KEY"))
        produccion = None
        if os.environ.get("DATABASE_URL", "").strip():
            produccion = respaldos.parsear_database_url(os.environ["DATABASE_URL"])
        destino = None
        if args.destino:
            destino = respaldos.parsear_database_url(args.destino)
        elif args.destino_local:
            destino = respaldos.conexion_desde_entorno({k: v for k, v in os.environ.items() if k != "DATABASE_URL"})
        secretos = [c.password for c in (produccion, destino) if c is not None]
        log = respaldos.configurar_logging(secretos=secretos)

        if destino is not None:
            hosts_extra = os.environ.get("BACKUP_HOSTS_PRODUCCION", "").split(",")
            try:
                autorizado = respaldos.autorizar_destino(
                    destino, produccion, args.confirmar_produccion, os.environ.get(VARIABLE_PRODUCCION, ""), hosts_extra,
                )
            except respaldos.ProduccionProtegidaError as exc:
                log.error("%s", exc)
                return 2
            if autorizado:
                log.warning("ADVERTENCIA: se va a restaurar sobre la base de PRODUCCION %s con doble confirmación. "
                            "Los datos actuales pueden quedar sobrescritos.", destino.descripcion())

        with respaldos.directorio_temporal() as tmp:
            tmp_dir = Path(tmp)
            os.chmod(tmp_dir, 0o700)
            cifrado, manifiesto = _obtener_respaldo(args, tmp_dir)
            log.info("Respaldo %s del %s (última migración %s, %d anclas de auditoría)",
                     respaldos.texto_para_log(manifiesto["nombre"]),
                     respaldos.texto_para_log(manifiesto["fecha_utc"]),
                     respaldos.texto_para_log(manifiesto["ultima_migracion"]),
                     len(manifiesto["anclas_auditoria"]))
            if args.solo_descifrar:
                volcado = respaldos.ruta_segura(args.solo_descifrar, para_escritura=True)
            else:
                # Revalidación explícita e inline en el punto de uso (además de la ya
                # realizada en validar_estructura_manifiesto): el nombre del manifiesto
                # no puede contener separadores de ruta ni componentes "..".
                nombre_volcado = str(manifiesto["nombre"])
                if not re.fullmatch(respaldos.PATRON_NOMBRE.pattern, nombre_volcado):
                    raise respaldos.RespaldoError("Nombre de respaldo en el manifiesto no válido.")
                volcado = tmp_dir / (nombre_volcado + ".dump")
            if args.solo_descifrar and volcado.exists():
                raise respaldos.RespaldoError(f"La ruta {volcado} ya existe; no se sobrescribe.")
            volcado.touch(mode=0o600)
            resultado = respaldos.verificar_respaldo(cifrado, manifiesto, clave, volcado)
            log.info("Verificación correcta: firma HMAC, SHA-256 cifrado %s, SHA-256 volcado %s (%d bytes)",
                     resultado["sha256_cifrado"][:16], resultado["sha256_plano"][:16], resultado["bytes_plano"])
            if args.verificar_solo:
                log.info("Modo verificación: no se restauró nada.")
                return 0
            if args.solo_descifrar:
                log.info("Volcado descifrado escrito en %s (permisos 0600). Bórrelo al terminar.", volcado)
                return 0
            if args.crear_base and respaldos.crear_base_si_no_existe(destino):
                log.info("Base destino %s creada.", destino.base)
            log.info("Ejecutando pg_restore sobre %s%s", destino.descripcion(), " (--clean)" if args.limpiar else "")
            avisos = respaldos.ejecutar_pg_restore(destino, volcado, limpiar=args.limpiar)
            if avisos:
                log.warning("pg_restore reportó avisos: %s", avisos)
            coincide, detalle = respaldos.comparar_migraciones(destino, manifiesto)
            if not coincide:
                raise respaldos.IntegridadError(f"Las migraciones restauradas no coinciden con el manifiesto: {detalle}.")
            log.info("Restauración completada en %s: %s.", destino.descripcion(),
                     respaldos.texto_para_log(detalle))
            for ancla in manifiesto["anclas_auditoria"]:
                log.info("Ancla de auditoría restaurada: licencia %s seq %s hash %s",
                         respaldos.texto_para_log(ancla["licenciaid"]),
                         respaldos.texto_para_log(ancla["ultimo_seq"]),
                         respaldos.texto_para_log(ancla["ultimo_hash"]))
            return 0
    except respaldos.RespaldoError as exc:
        log.error("Restauración fallida: %s", exc)
        return 1
    except OSError as exc:
        log.error("Error de sistema durante la restauración: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
