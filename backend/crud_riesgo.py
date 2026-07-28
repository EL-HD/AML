"""
crud_riesgo.py — Acceso a datos para la Administración de Riesgo Institucional
de LD/FT (segmentación, eventos, controles, planes de acción).

Reglas de seguridad (OWASP A01 — control de acceso roto / IDOR):
  * TODA consulta, actualización o eliminación filtra siempre por
    `licenciaid` además del id del registro. Un usuario autenticado jamás
    puede leer ni modificar datos de otra Persona Obligada (otra licencia),
    incluso si adivina o manipula un UUID de otro registro.
  * `licenciaid` debe provenir siempre del lado servidor (JWT / sesión
    autenticada — `st.session_state.user_data["licence_id"]`), nunca de un
    campo de texto editable por el usuario.
  * Todo acceso a la base de datos usa el ORM de SQLAlchemy con parámetros
    ligados (sin construir SQL por concatenación de strings) — previene
    inyección SQL (OWASP A03).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from . import models, riesgo_ldft_logic as logic


def _as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


# ── Segmentación ─────────────────────────────────────────────────────────

def crear_segmento(db: Session, licenciaid, factor: str, segmento: str, variable: str, creado_por: str) -> models.RiesgoSegmento:
    row = models.RiesgoSegmento(
        licenciaid=_as_uuid(licenciaid),
        factor=factor,
        segmento=segmento.strip(),
        variable=variable.strip(),
        creado_por=creado_por,
        creado_en=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listar_segmentos(db: Session, licenciaid):
    return (
        db.query(models.RiesgoSegmento)
        .filter(models.RiesgoSegmento.licenciaid == _as_uuid(licenciaid))
        .order_by(models.RiesgoSegmento.factor, models.RiesgoSegmento.segmento)
        .all()
    )


def eliminar_segmento(db: Session, licenciaid, segmento_id) -> bool:
    row = (
        db.query(models.RiesgoSegmento)
        .filter(models.RiesgoSegmento.id == _as_uuid(segmento_id), models.RiesgoSegmento.licenciaid == _as_uuid(licenciaid))
        .first()
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ── Eventos de riesgo ────────────────────────────────────────────────────

def _generar_codigo_evento(db: Session, licenciaid) -> str:
    total = db.query(models.RiesgoEvento).filter(models.RiesgoEvento.licenciaid == _as_uuid(licenciaid)).count()
    return f"E{total + 1:05d}"


def crear_evento(db: Session, licenciaid, data, creado_por: str) -> models.RiesgoEvento:
    """`data` es una instancia validada de schemas.RiesgoEventoCreate."""
    impacto = logic.calcular_impacto(
        data.riesgo_operacional, data.riesgo_legal, data.riesgo_reputacional, data.riesgo_contagio
    )
    nivel_inherente = logic.nivel_desde_producto(data.probabilidad, impacto)

    segmento_id = None
    if data.segmento_id is not None:
        seg = (
            db.query(models.RiesgoSegmento)
            .filter(models.RiesgoSegmento.id == data.segmento_id, models.RiesgoSegmento.licenciaid == _as_uuid(licenciaid))
            .first()
        )
        if seg:
            segmento_id = seg.id

    row = models.RiesgoEvento(
        licenciaid=_as_uuid(licenciaid),
        codigo=_generar_codigo_evento(db, licenciaid),
        nombre=data.nombre.strip(),
        descripcion=(data.descripcion or "").strip() or None,
        factor=data.factor,
        segmento_id=segmento_id,
        probabilidad=data.probabilidad,
        riesgo_operacional=data.riesgo_operacional,
        riesgo_legal=data.riesgo_legal,
        riesgo_reputacional=data.riesgo_reputacional,
        riesgo_contagio=data.riesgo_contagio,
        impacto=impacto,
        nivel_inherente=nivel_inherente,
        nivel_residual=nivel_inherente,  # sin controles vinculados aún = inherente
        requiere_plan_accion=logic.requiere_plan_de_accion(nivel_inherente),
        creado_por=creado_por,
        creado_en=datetime.now(),
        actualizado_en=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listar_eventos(db: Session, licenciaid):
    return (
        db.query(models.RiesgoEvento)
        .filter(models.RiesgoEvento.licenciaid == _as_uuid(licenciaid))
        .order_by(models.RiesgoEvento.creado_en.desc())
        .all()
    )


def obtener_evento(db: Session, licenciaid, evento_id) -> Optional[models.RiesgoEvento]:
    return (
        db.query(models.RiesgoEvento)
        .filter(models.RiesgoEvento.id == _as_uuid(evento_id), models.RiesgoEvento.licenciaid == _as_uuid(licenciaid))
        .first()
    )


def eliminar_evento(db: Session, licenciaid, evento_id) -> bool:
    row = obtener_evento(db, licenciaid, evento_id)
    if not row:
        return False
    db.query(models.RiesgoEventoControl).filter(
        models.RiesgoEventoControl.evento_id == row.id, models.RiesgoEventoControl.licenciaid == _as_uuid(licenciaid)
    ).delete()
    db.query(models.RiesgoPlanAccion).filter(
        models.RiesgoPlanAccion.evento_id == row.id, models.RiesgoPlanAccion.licenciaid == _as_uuid(licenciaid)
    ).delete()
    db.delete(row)
    db.commit()
    return True


# ── Controles / mitigadores ──────────────────────────────────────────────

def crear_control(db: Session, licenciaid, data, creado_por: str) -> models.RiesgoControl:
    """`data` es una instancia validada de schemas.RiesgoControlCreate."""
    ponderacion = logic.calcular_ponderacion_control(
        documentado=data.documentado,
        tipo_control=data.tipo_control,
        ejecucion=data.ejecucion,
        nivel_cumplimiento=data.nivel_cumplimiento,
        nivel_efectividad=data.nivel_efectividad,
    )
    nivel_ponderacion = logic.nivel_desde_ponderacion(ponderacion)

    row = models.RiesgoControl(
        licenciaid=_as_uuid(licenciaid),
        nombre=data.nombre.strip(),
        descripcion=data.descripcion.strip(),
        documentado=data.documentado,
        tipo_control=data.tipo_control,
        ejecucion=data.ejecucion,
        nivel_cumplimiento=data.nivel_cumplimiento,
        nivel_efectividad=data.nivel_efectividad,
        evaluado=data.evaluado,
        responsable_evaluacion=(data.responsable_evaluacion or "").strip() or None,
        fecha_evaluacion=data.fecha_evaluacion,
        ponderacion=ponderacion,
        nivel_ponderacion=nivel_ponderacion,
        creado_por=creado_por,
        creado_en=datetime.now(),
        actualizado_en=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listar_controles(db: Session, licenciaid):
    return (
        db.query(models.RiesgoControl)
        .filter(models.RiesgoControl.licenciaid == _as_uuid(licenciaid))
        .order_by(models.RiesgoControl.creado_en.desc())
        .all()
    )


def eliminar_control(db: Session, licenciaid, control_id) -> bool:
    row = (
        db.query(models.RiesgoControl)
        .filter(models.RiesgoControl.id == _as_uuid(control_id), models.RiesgoControl.licenciaid == _as_uuid(licenciaid))
        .first()
    )
    if not row:
        return False
    eventos_afectados = [
        rel.evento_id for rel in db.query(models.RiesgoEventoControl).filter(
            models.RiesgoEventoControl.control_id == row.id, models.RiesgoEventoControl.licenciaid == _as_uuid(licenciaid)
        ).all()
    ]
    db.query(models.RiesgoEventoControl).filter(
        models.RiesgoEventoControl.control_id == row.id, models.RiesgoEventoControl.licenciaid == _as_uuid(licenciaid)
    ).delete()
    db.delete(row)
    db.commit()
    for evento_id in eventos_afectados:
        _recalcular_riesgo_residual(db, licenciaid, evento_id)
    return True


# ── Vínculo evento <-> control ───────────────────────────────────────────

def _recalcular_riesgo_residual(db: Session, licenciaid, evento_id) -> Optional[models.RiesgoEvento]:
    evento = obtener_evento(db, licenciaid, evento_id)
    if not evento:
        return None
    controles = controles_de_evento(db, licenciaid, evento_id)
    niveles = [c.nivel_ponderacion for c in controles]
    nuevo_residual = logic.calcular_riesgo_residual(evento.nivel_inherente, niveles)
    evento.nivel_residual = nuevo_residual
    evento.requiere_plan_accion = logic.requiere_plan_de_accion(nuevo_residual)
    evento.actualizado_en = datetime.now()
    db.commit()
    db.refresh(evento)
    return evento


def vincular_control(db: Session, licenciaid, evento_id, control_id) -> Optional[models.RiesgoEvento]:
    lid = _as_uuid(licenciaid)
    evento = obtener_evento(db, lid, evento_id)
    control = (
        db.query(models.RiesgoControl)
        .filter(models.RiesgoControl.id == _as_uuid(control_id), models.RiesgoControl.licenciaid == lid)
        .first()
    )
    if not evento or not control:
        return None  # evita IDOR: alguno de los dos no pertenece a esta licencia

    ya_vinculado = (
        db.query(models.RiesgoEventoControl)
        .filter(
            models.RiesgoEventoControl.evento_id == evento.id,
            models.RiesgoEventoControl.control_id == control.id,
            models.RiesgoEventoControl.licenciaid == lid,
        )
        .first()
    )
    if not ya_vinculado:
        db.add(models.RiesgoEventoControl(
            licenciaid=lid, evento_id=evento.id, control_id=control.id, creado_en=datetime.now()
        ))
        db.commit()
    return _recalcular_riesgo_residual(db, lid, evento.id)


def desvincular_control(db: Session, licenciaid, evento_id, control_id) -> Optional[models.RiesgoEvento]:
    lid = _as_uuid(licenciaid)
    db.query(models.RiesgoEventoControl).filter(
        models.RiesgoEventoControl.evento_id == _as_uuid(evento_id),
        models.RiesgoEventoControl.control_id == _as_uuid(control_id),
        models.RiesgoEventoControl.licenciaid == lid,
    ).delete()
    db.commit()
    return _recalcular_riesgo_residual(db, lid, evento_id)


def controles_de_evento(db: Session, licenciaid, evento_id):
    lid = _as_uuid(licenciaid)
    ids_control = [
        rel.control_id for rel in db.query(models.RiesgoEventoControl).filter(
            models.RiesgoEventoControl.evento_id == _as_uuid(evento_id),
            models.RiesgoEventoControl.licenciaid == lid,
        ).all()
    ]
    if not ids_control:
        return []
    return (
        db.query(models.RiesgoControl)
        .filter(models.RiesgoControl.id.in_(ids_control), models.RiesgoControl.licenciaid == lid)
        .all()
    )


def eventos_de_control(db: Session, licenciaid, control_id):
    lid = _as_uuid(licenciaid)
    ids_evento = [
        rel.evento_id for rel in db.query(models.RiesgoEventoControl).filter(
            models.RiesgoEventoControl.control_id == _as_uuid(control_id),
            models.RiesgoEventoControl.licenciaid == lid,
        ).all()
    ]
    if not ids_evento:
        return []
    return (
        db.query(models.RiesgoEvento)
        .filter(models.RiesgoEvento.id.in_(ids_evento), models.RiesgoEvento.licenciaid == lid)
        .all()
    )


# ── Plan de acción ───────────────────────────────────────────────────────

def crear_plan_accion(db: Session, licenciaid, evento_id, data, creado_por: str) -> Optional[models.RiesgoPlanAccion]:
    """`data` es una instancia validada de schemas.RiesgoPlanAccionCreate."""
    lid = _as_uuid(licenciaid)
    evento = obtener_evento(db, lid, evento_id)
    if not evento:
        return None
    row = models.RiesgoPlanAccion(
        licenciaid=lid,
        evento_id=evento.id,
        medida_propuesta=data.medida_propuesta.strip(),
        responsable=data.responsable.strip(),
        fecha_inicio=data.fecha_inicio,
        fecha_fin=data.fecha_fin,
        porcentaje_avance=data.porcentaje_avance,
        creado_por=creado_por,
        creado_en=datetime.now(),
        actualizado_en=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listar_planes(db: Session, licenciaid):
    return (
        db.query(models.RiesgoPlanAccion)
        .filter(models.RiesgoPlanAccion.licenciaid == _as_uuid(licenciaid))
        .order_by(models.RiesgoPlanAccion.fecha_fin)
        .all()
    )


def planes_de_evento(db: Session, licenciaid, evento_id):
    return (
        db.query(models.RiesgoPlanAccion)
        .filter(
            models.RiesgoPlanAccion.evento_id == _as_uuid(evento_id),
            models.RiesgoPlanAccion.licenciaid == _as_uuid(licenciaid),
        )
        .all()
    )


def actualizar_avance_plan(db: Session, licenciaid, plan_id, porcentaje_avance: int) -> Optional[models.RiesgoPlanAccion]:
    porcentaje_avance = max(0, min(100, int(porcentaje_avance)))
    row = (
        db.query(models.RiesgoPlanAccion)
        .filter(models.RiesgoPlanAccion.id == _as_uuid(plan_id), models.RiesgoPlanAccion.licenciaid == _as_uuid(licenciaid))
        .first()
    )
    if not row:
        return None
    row.porcentaje_avance = porcentaje_avance
    row.actualizado_en = datetime.now()
    db.commit()
    db.refresh(row)
    return row


# ── Resultados / KPIs (módulo administrativo) ────────────────────────────

def eventos_sin_segmentar(db: Session, licenciaid):
    return (
        db.query(models.RiesgoEvento)
        .filter(models.RiesgoEvento.licenciaid == _as_uuid(licenciaid), models.RiesgoEvento.segmento_id.is_(None))
        .all()
    )


def eventos_sin_control(db: Session, licenciaid):
    lid = _as_uuid(licenciaid)
    ids_con_control = {
        rel.evento_id for rel in db.query(models.RiesgoEventoControl).filter(models.RiesgoEventoControl.licenciaid == lid).all()
    }
    return [e for e in listar_eventos(db, lid) if e.id not in ids_con_control]


def eventos_sin_plan(db: Session, licenciaid):
    lid = _as_uuid(licenciaid)
    ids_con_plan = {p.evento_id for p in listar_planes(db, lid)}
    return [
        e for e in listar_eventos(db, lid)
        if e.requiere_plan_accion and e.id not in ids_con_plan
    ]


def controles_sin_evento(db: Session, licenciaid):
    lid = _as_uuid(licenciaid)
    ids_con_evento = {
        rel.control_id for rel in db.query(models.RiesgoEventoControl).filter(models.RiesgoEventoControl.licenciaid == lid).all()
    }
    return [c for c in listar_controles(db, lid) if c.id not in ids_con_evento]
