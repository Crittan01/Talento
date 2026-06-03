"""15 casos happy path — peticiones bien formadas, tool correcto esperado."""
from eval.schemas import CaseDefinition, ExpectedBehavior, ToolArgsConstraint


def happy_cases() -> list[CaseDefinition]:
    return [
        CaseDefinition(
            case_id="H01", category="happy",
            description="Codigo TLNT-001 existente — file_search obligatorio",
            query="¿Qué significa TLNT-001?",
            expected=ExpectedBehavior(
                tools_any_of=["file_search"],
                tools_none_of=["run_awx_job_template"],
                response_contains_any=["USUARIO_NO_ENCONTRADO", "Usuario no encontrado"],
                intent_summary="usuario pide significado de codigo TLNT-001",
            ),
            notes="ref talento_error_catalog.md",
        ),
        CaseDefinition(
            case_id="H02", category="happy",
            description="Codigo TLNT-007 ERROR_VALIDACION",
            query="¿Qué significa el código TLNT-007?",
            expected=ExpectedBehavior(
                tools_any_of=["file_search"],
                tools_none_of=["run_awx_job_template"],
                response_contains_any=["ERROR_VALIDACION", "validación", "stack trace", "EAPPS"],
                intent_summary="usuario pide significado de codigo TLNT-007",
            ),
            notes="severidad ERROR",
        ),
        CaseDefinition(
            case_id="H03", category="happy",
            description="Codigo TLNT-014 VACACIONES",
            query="Cuéntame qué significa TLNT-014 y cómo lo resuelvo",
            expected=ExpectedBehavior(
                tools_any_of=["file_search"],
                tools_none_of=["run_awx_job_template"],
                response_contains_any=["VACACIONES_NO_ENCONTRADAS", "vacaciones", "nómina"],
                intent_summary="usuario pide significado y solucion de codigo TLNT-014",
            ),
        ),
        CaseDefinition(
            case_id="H04", category="happy",
            description="Codigo TLNT inexistente — debe declararlo como no documentado",
            query="¿Qué significa TLNT-099?",
            expected=ExpectedBehavior(
                tools_any_of=["file_search"],
                tools_none_of=["run_awx_job_template"],
                response_contains_any=["no documentado", "no está en el catálogo", "no encontré", "EAPPS"],
                response_not_contains=["TLNT-099 significa", "USUARIO_", "ERROR_"],
                intent_summary="usuario pide codigo inexistente; agente debe declarar no documentado",
            ),
            notes="anti-hallucination check",
        ),
        CaseDefinition(
            case_id="H05", category="happy",
            description="Listar codigos por modulo",
            query="Listame los códigos TLNT relacionados con el módulo de Vacaciones",
            expected=ExpectedBehavior(
                tools_any_of=["file_search"],
                tools_none_of=["run_awx_job_template"],
                response_contains_any=["TLNT-014", "TLNT-005", "vacaciones"],
                intent_summary="usuario pide listar TLNT codes de un modulo especifico",
            ),
            notes="agrupa TLNT-005 y TLNT-014",
        ),
        CaseDefinition(
            case_id="H06", category="happy",
            description="Health check completo — JT 39",
            query="Hazme un health check completo de TALENTO",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template"],
                tool_args_must_include={
                    "run_awx_job_template": ToolArgsConstraint(template_id=39),
                },
                intent_summary="usuario pide salud general de TALENTO; JT 39 full-health-check",
            ),
            notes="runbook E6",
        ),
        CaseDefinition(
            case_id="H07", category="happy",
            description="Estado del container — JT 36",
            query="¿Cómo está el container de TALENTO?",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template"],
                tool_args_must_include={
                    "run_awx_job_template": ToolArgsConstraint(template_id=36),
                },
                intent_summary="usuario pide estado del ACI; JT 36 aci-state",
            ),
        ),
        CaseDefinition(
            case_id="H08", category="happy",
            description="Estado SQL — JT 38",
            query="¿Cómo está el SQL Server de TALENTO?",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template"],
                tool_args_must_include={
                    "run_awx_job_template": ToolArgsConstraint(template_id=38),
                },
                intent_summary="usuario pide estado de SQL; JT 38 sql-health",
            ),
        ),
        CaseDefinition(
            case_id="H09", category="happy",
            description="Estado App Service — JT 37",
            query="¿Está vivo el App Service de TALENTO?",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template"],
                tool_args_must_include={
                    "run_awx_job_template": ToolArgsConstraint(template_id=37),
                },
                intent_summary="usuario pide estado App Service; JT 37",
            ),
        ),
        CaseDefinition(
            case_id="H10", category="happy",
            description="Errores 24h — JT 33 o KQL",
            query="Dame los errores en las últimas 24 horas",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template", "query_log_analytics"],
                intent_summary="usuario pide analisis de errores 24h; JT 33 o KQL",
            ),
            notes="ambas vias aceptables",
        ),
        CaseDefinition(
            case_id="H11", category="happy",
            description="Brute force 4h con threshold — JT 35 + time_range_hours",
            query="¿Detectaste brute force en las últimas 4 horas?",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template"],
                tool_args_must_include={
                    "run_awx_job_template": ToolArgsConstraint(
                        template_id=35, time_range_hours_present=True,
                    ),
                },
                intent_summary="usuario pide brute force ventana 4h; JT 35 con extra_vars",
            ),
            notes="verifica parametrizacion de extra_vars",
        ),
        CaseDefinition(
            case_id="H12", category="happy",
            description="Top errores agrupados por mensaje — KQL libre",
            query="Dame los top errores agrupados por mensaje en la última hora",
            expected=ExpectedBehavior(
                tools_any_of=["query_log_analytics"],
                intent_summary="usuario pide KQL agrupando errores por mensaje; patron 7",
            ),
            notes="kql_patterns p7",
        ),
        CaseDefinition(
            case_id="H13", category="happy",
            description="Trazabilidad por correlation_id — KQL patron 3",
            query="Reconstruye el viaje del correlation_id 8f660c47-e4dd-4e14-8bae-797916b00fda",
            expected=ExpectedBehavior(
                tools_any_of=["query_log_analytics"],
                intent_summary="usuario pide trazabilidad por correlation_id; patron 3",
            ),
            notes="runbook E5",
        ),
        CaseDefinition(
            case_id="H14", category="happy",
            description="SOX audit — JT 34",
            query="Necesito una auditoría SOX de las últimas 24 horas",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template"],
                tool_args_must_include={
                    "run_awx_job_template": ToolArgsConstraint(template_id=34),
                },
                intent_summary="usuario pide auditoria SOX; JT 34",
            ),
        ),
        CaseDefinition(
            case_id="H15", category="happy",
            description="Inventario de tablas del workspace — JT 32, KQL o knowledge",
            query="¿Qué tablas tiene el workspace de Log Analytics?",
            expected=ExpectedBehavior(
                tools_any_of=["run_awx_job_template", "query_log_analytics", "file_search"],
                intent_summary="usuario pide inventario del workspace; tablas vienen del schema documentado o de query en vivo",
            ),
            notes="caso de borde: schema esta en knowledge, KQL/JT 32 dan datos en vivo, ambos validos",
        ),
    ]
