# Reporte — Permisos del Service Principal para auto-remediacion

_Generado por `scripts/probe-aci-permissions.py` (READ-ONLY)._

- **Subscription**: `7c5b032f-7879-4ec3-a2ed-978b444f6755`
- **Resource Group**: `rg-central-solucion-talento`
- **Service Principal (Client ID)**: `bbd498f7-caed-4daa-a236-f12fd3a13461`

## 1. Recursos visibles desde el SP

### Container Instances
X **El SP no puede listar containers en el RG** — falta `Microsoft.ContainerInstance/containerGroups/read`.

### App Services
X **El SP no puede listar App Services en el RG** — falta `Microsoft.Web/sites/read`.

## 2. Cross-check de acciones necesarias para auto-remediacion

| Nivel | Accion | Proposito | Permitido |
|---|---|---|---|
| 1-container | `Microsoft.ContainerInstance/containerGroups/read` | Leer estado/config del container | **FALTA** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/restart/action` | Reiniciar container (REMEDIACION) | **FALTA** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/stop/action` | Detener container (REMEDIACION) | **FALTA** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/start/action` | Iniciar container (REMEDIACION) | **FALTA** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/containers/logs/action` | Leer logs en vivo del container | **FALTA** |
| 1-appservice | `Microsoft.Web/sites/read` | Leer estado del App Service | **FALTA** |
| 1-appservice | `Microsoft.Web/sites/restart/action` | Reiniciar App Service (REMEDIACION) | **FALTA** |
| 2-sql | `Microsoft.Sql/servers/read` | Leer estado del SQL Server | **FALTA** |
| 2-sql | `Microsoft.Sql/servers/databases/read` | Leer estado de la base de datos | **FALTA** |
| 0-baseline | `Microsoft.OperationalInsights/workspaces/read` | Leer Log Analytics workspace (baseline) | **FALTA** |
| 0-baseline | `Microsoft.OperationalInsights/workspaces/query/action` | Ejecutar KQL queries (baseline) | **FALTA** |

## 3. Permisos efectivos enumerados

El SP tiene 0 patron(es) de acciones permitidas en este RG:

_(ninguno enumerable via API)_

## 4. Recomendacion: que pedir al admin de Azure

Faltan **11 permisos** para cubrir el alcance completo.

### Opcion A - rol built-in (rapido)

Asignar `Contributor` al SP sobre `rg-central-solucion-talento`:

```bash
az role assignment create \
  --assignee bbd498f7-caed-4daa-a236-f12fd3a13461 \
  --role Contributor \
  --scope /subscriptions/7c5b032f-7879-4ec3-a2ed-978b444f6755/resourceGroups/rg-central-solucion-talento
```

Pros: 1 click en portal o un comando az. Cons: amplio (incluye delete, write de todo).

### Opcion B - custom role (restrictivo, recomendado)

Crear `TalentoAutoRemediator` solo con las acciones faltantes:

```json
{
  "Name": "TalentoAutoRemediator",
  "Description": "Permisos minimos para auto-remediacion del agente IA de TALENTO",
  "AssignableScopes": ["/subscriptions/7c5b032f-7879-4ec3-a2ed-978b444f6755/resourceGroups/rg-central-solucion-talento"],
  "Actions": [
    "Microsoft.ContainerInstance/containerGroups/read",
    "Microsoft.ContainerInstance/containerGroups/restart/action",
    "Microsoft.ContainerInstance/containerGroups/stop/action",
    "Microsoft.ContainerInstance/containerGroups/start/action",
    "Microsoft.ContainerInstance/containerGroups/containers/logs/action",
    "Microsoft.Web/sites/read",
    "Microsoft.Web/sites/restart/action",
    "Microsoft.Sql/servers/read",
    "Microsoft.Sql/servers/databases/read",
    "Microsoft.OperationalInsights/workspaces/read",
    "Microsoft.OperationalInsights/workspaces/query/action"
  ],
  "NotActions": [],
  "DataActions": [],
  "NotDataActions": []
}
```

Crear y asignar:

```bash
az role definition create --role-definition role.json
az role assignment create \
  --assignee bbd498f7-caed-4daa-a236-f12fd3a13461 \
  --role "TalentoAutoRemediator" \
  --scope /subscriptions/7c5b032f-7879-4ec3-a2ed-978b444f6755/resourceGroups/rg-central-solucion-talento
```

---

_Re-ejecutar `python3 scripts/probe-aci-permissions.py` despues de que el admin asigne el rol para confirmar._