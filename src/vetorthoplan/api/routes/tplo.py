from typing import Annotated

from fastapi import APIRouter, Depends, Query

from vetorthoplan.api.dependencies import (
    get_tenant_context,
    get_tplo_rotation_table_repository,
)
from vetorthoplan.api.schemas import TploClinicalProtocolResponse, TploRotationTableResponse
from vetorthoplan.application.ports.tplo_rotation_table_repository import TploRotationTableRepository
from vetorthoplan.config.settings import Settings, get_settings
from vetorthoplan.domain.planning.clinical_protocol import parse_clinical_protocol
from vetorthoplan.domain.planning.rotation_table import matches_numeric_filter, parse_rotation_table

router = APIRouter(prefix="/api/v1/tplo", dependencies=[Depends(get_tenant_context)])


@router.get(
    "/rotation-table",
    response_model=TploRotationTableResponse,
    tags=["Planning"],
    summary="Consultar tabela de referência de rotação TPLO",
    description=(
        "Retorna a versão ativa persistida no banco (ou uma substituição explicitamente configurada) "
        "e permite filtrar por TPA e diâmetro da lâmina. A consulta usa correspondência exata; não "
        "interpola nem recomenda uma rotação cirúrgica."
    ),
)
async def get_tplo_rotation_table(
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[TploRotationTableRepository, Depends(get_tplo_rotation_table_repository)],
    tpa_degrees: float | None = Query(default=None, ge=0, le=90),
    blade_diameter_mm: float | None = Query(default=None, gt=0),
) -> TploRotationTableResponse:
    table = parse_rotation_table(
        settings.tplo_rotation_table_version,
        settings.tplo_rotation_table_source,
        settings.tplo_rotation_table_json,
    )
    if table is None:
        table = await repository.get_active()
    query = {
        key: value
        for key, value in (
            ("tpa_degrees", tpa_degrees),
            ("blade_diameter_mm", blade_diameter_mm),
        )
        if value is not None
    }
    entries = table.entries if table is not None else []
    for key, value in query.items():
        entries = [row for row in entries if matches_numeric_filter(row.get(key), value)]

    return TploRotationTableResponse(
        configured=table is not None,
        table_version=table.version if table is not None else None,
        source=table.source if table is not None else None,
        source_url=table.source_url if table is not None else None,
        source_asset_url=table.source_asset_url if table is not None else None,
        target_slope_degrees=table.target_slope_degrees if table is not None else None,
        entries_sha256=table.entries_sha256 if table is not None else None,
        query=query,
        match_count=len(entries),
        entries=entries,
    )


@router.get(
    "/clinical-protocol",
    response_model=TploClinicalProtocolResponse,
    tags=["Planning"],
    summary="Consultar protocolo de medidas clínicas TPLO",
    description=(
        "Retorna definições e tolerâncias versionadas configuradas pelo ambiente. "
        "A consulta não homologa o protocolo nem recomenda conduta clínica."
    ),
)
async def get_tplo_clinical_protocol(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TploClinicalProtocolResponse:
    protocol = parse_clinical_protocol(settings.tplo_clinical_protocol_json)
    if protocol is None:
        return TploClinicalProtocolResponse(configured=False)
    return TploClinicalProtocolResponse(
        configured=True,
        protocol_version=protocol.version,
        source=protocol.source,
        measurements=[measurement.model_dump(mode="json") for measurement in protocol.measurements],
        acceptance_enabled=protocol.tpa_max_absolute_error_degrees is not None or bool(protocol.measurements),
    )
