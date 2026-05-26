# Reporte — Permisos del Service Principal para auto-remediacion

_Generado por `scripts/probe-aci-permissions.py` (READ-ONLY)._

- **Subscription**: `7c5b032f-7879-4ec3-a2ed-978b444f6755`
- **Resource Group**: `rg-central-solucion-talento`
- **Service Principal (Client ID)**: `bbd498f7-caed-4daa-a236-f12fd3a13461`

## 1. Recursos visibles desde el SP

### Container Instances
| Nombre | Estado |
|---|---|
| `aci-centralecopetrol` | `?` |

### App Services
| Nombre |
|---|
| `app-central-ecopetrol` |

## 2. Cross-check de acciones necesarias para auto-remediacion

| Nivel | Accion | Proposito | Permitido |
|---|---|---|---|
| 1-container | `Microsoft.ContainerInstance/containerGroups/read` | Leer estado/config del container | **OK** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/restart/action` | Reiniciar container (REMEDIACION) | **OK** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/stop/action` | Detener container (REMEDIACION) | **OK** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/start/action` | Iniciar container (REMEDIACION) | **OK** |
| 1-container | `Microsoft.ContainerInstance/containerGroups/containers/logs/action` | Leer logs en vivo del container | **OK** |
| 1-appservice | `Microsoft.Web/sites/read` | Leer estado del App Service | **OK** |
| 1-appservice | `Microsoft.Web/sites/restart/action` | Reiniciar App Service (REMEDIACION) | **OK** |
| 2-sql | `Microsoft.Sql/servers/read` | Leer estado del SQL Server | **OK** |
| 2-sql | `Microsoft.Sql/servers/databases/read` | Leer estado de la base de datos | **OK** |
| 0-baseline | `Microsoft.OperationalInsights/workspaces/read` | Leer Log Analytics workspace (baseline) | **OK** |
| 0-baseline | `Microsoft.OperationalInsights/workspaces/query/action` | Ejecutar KQL queries (baseline) | **OK** |

## 3. Permisos efectivos enumerados

El SP tiene 10 patron(es) de acciones permitidas en este RG:

```
*
Microsoft.ContainerInstance/containerGroups/read
Microsoft.ContainerInstance/containerGroups/restart/action
Microsoft.ContainerInstance/containerGroups/start/action
Microsoft.ContainerInstance/containerGroups/stop/action
Microsoft.OperationalInsights/workspaces/read
Microsoft.Sql/servers/databases/read
Microsoft.Sql/servers/read
Microsoft.Web/sites/Read
Microsoft.Web/sites/restart/Action
```

Y 11 patron(es) excluidas (notActions):

```
Microsoft.Authorization/*/Delete
Microsoft.Authorization/*/Write
Microsoft.Authorization/elevateAccess/Action
Microsoft.Blueprint/blueprintAssignments/delete
Microsoft.Blueprint/blueprintAssignments/write
Microsoft.Compute/galleries/share/action
Microsoft.Purview/consents/delete
Microsoft.Purview/consents/write
Microsoft.Resources/deploymentStacks/manageDenySetting/action
Microsoft.Subscription/cancel/action
Microsoft.Subscription/enable/action
```

## 4. Recomendacion: que pedir al admin de Azure

**No hace falta escalar.** El SP ya tiene todos los permisos necesarios.

---

_Re-ejecutar `python3 scripts/probe-aci-permissions.py` despues de que el admin asigne el rol para confirmar._