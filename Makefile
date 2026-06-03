# Makefile — talento-ecopetrol Operations Console
# Orquestador del workflow demo + dev. Ejecuta `make help` para ver todo.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Color helpers
C_GREEN  := \033[0;32m
C_YELLOW := \033[1;33m
C_CYAN   := \033[0;36m
C_RED    := \033[0;31m
C_RESET  := \033[0m

# Carga .env si existe (no pone los valores en make-vars, los pasa al shell)
ENV_LOAD := if [ -f .env ]; then set -a; source .env; set +a; fi

.PHONY: help install dev demo mock cli test awx-sync awx-status inject-demo \
        stop clean rotate-secret-check repo-status pre-demo \
        demo-local demo-azure profile-show profile-local profile-azure

help:  ## Lista todos los targets disponibles
	@echo ""
	@printf "$(C_CYAN)talento-ecopetrol — Operations Console$(C_RESET)\n"
	@echo ""
	@printf "$(C_YELLOW)Uso:$(C_RESET) make <target>\n"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(C_GREEN)%-22s$(C_RESET) %s\n", $$1, $$2}'
	@echo ""

install:  ## Instala/actualiza paquetes Python necesarios
	pip3 install --user --upgrade \
		fastapi uvicorn jinja2 \
		azure-ai-projects azure-identity openai requests
	@echo ""
	@printf "$(C_GREEN)✓ Dependencias instaladas$(C_RESET)\n"

dev:  ## Levanta dashboard en modo desarrollo (uvicorn --reload)
	@$(ENV_LOAD); \
	echo "$(C_CYAN)Dashboard en modo dev — http://localhost:8000$(C_RESET)"; \
	echo "$(C_YELLOW)Ctrl+C para detener.$(C_RESET)"; \
	uvicorn webapp.app:app --host 0.0.0.0 --port 8000 --reload

demo:  ## Levanta dashboard production-like (sin reload) para la presentacion
	@$(ENV_LOAD); \
	echo "$(C_CYAN)Dashboard listo para demo — http://localhost:8000$(C_RESET)"; \
	echo "$(C_YELLOW)Ctrl+C para detener.$(C_RESET)"; \
	uvicorn webapp.app:app --host 0.0.0.0 --port 8000 --log-level info

mock:  ## Levanta dashboard con FORCE_MOCK=1 (eventos pregrabados, sin tocar AWX/Foundry)
	@$(ENV_LOAD); \
	echo "$(C_YELLOW)MODO MOCK ACTIVO — eventos pregrabados, no toca Azure/AWX/Teams$(C_RESET)"; \
	echo "$(C_CYAN)Dashboard mock — http://localhost:8000$(C_RESET)"; \
	FORCE_MOCK=1 uvicorn webapp.app:app --host 0.0.0.0 --port 8000 --log-level info

cli:  ## Ejecuta bridge_l2 desde CLI. Uso: make cli Q=5
	@$(ENV_LOAD); \
	python3 bridge_l2.py $(Q) --no-setup

test:  ## Smoke tests: az, AWX, Foundry, paquetes Python, webapp importable
	@./scripts/validate.sh

awx-sync:  ## Re-sync del project 46 en AWX (despues de un push al repo)
	@$(ENV_LOAD); \
	curl -ks -X POST -H "Authorization: Bearer $$AWX_TOKEN" \
		"$$AWX_URL/api/v2/projects/46/update/" > /dev/null && \
	echo "$(C_GREEN)✓ Sync disparado. Verifica con: make awx-status$(C_RESET)"

awx-status:  ## Resumen del estado de AWX (projects, JTs, jobs recientes)
	@./scripts/awx-status.sh

inject-demo:  ## Inyecta datos sinteticos de brute force al workspace (opcional pre-demo)
	@./scripts/inject-synthetic-bruteforce.sh

stop:  ## Mata procesos uvicorn activos del dashboard
	@if pkill -f "uvicorn webapp.app" 2>/dev/null; then \
		printf "$(C_GREEN)✓ uvicorn detenido$(C_RESET)\n"; \
	else \
		printf "$(C_YELLOW)No estaba corriendo$(C_RESET)\n"; \
	fi

clean:  ## Borra __pycache__/ y logs temporales
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -f /tmp/bridge_l2_*.log 2>/dev/null || true
	@printf "$(C_GREEN)✓ Limpieza completa$(C_RESET)\n"

rotate-secret-check:  ## Recordatorio sobre el AZURE_CLIENT_SECRET expuesto en historia
	@printf "$(C_YELLOW)═══════════════════════════════════════════════════════════════════════$(C_RESET)\n"
	@printf "$(C_YELLOW)  RECORDATORIO de seguridad$(C_RESET)\n"
	@printf "$(C_YELLOW)═══════════════════════════════════════════════════════════════════════$(C_RESET)\n"
	@echo "  El AZURE_CLIENT_SECRET y el AWX_TOKEN aparecen en el chat history"
	@echo "  del desarrollo y fueron detectados por GitHub Secret Scanning en"
	@echo "  un push previo (commit rechazado, secret nunca subido al repo)."
	@echo ""
	@echo "  Antes de pasar a produccion o a demo externa:"
	@echo "    1. Rota AZURE_CLIENT_SECRET en Azure Portal → App registration"
	@echo "       bbd498f7-caed-4daa-a236-f12fd3a13461 → Certificates & secrets"
	@echo "    2. Rota AWX_TOKEN en la UI de AWX → tu usuario → Tokens"
	@echo "    3. Actualiza .env con los valores nuevos"
	@echo "    4. Corre 'make test' para validar"
	@printf "$(C_YELLOW)═══════════════════════════════════════════════════════════════════════$(C_RESET)\n"

repo-status:  ## Estado del repo: branch, commits pendientes, archivos modificados
	@echo ""
	@printf "$(C_CYAN)── Branch ──$(C_RESET)\n"
	@git branch --show-current
	@echo ""
	@printf "$(C_CYAN)── Commits locales sin push ──$(C_RESET)\n"
	@git log --oneline @{u}..HEAD 2>/dev/null || git log --oneline -5
	@echo ""
	@printf "$(C_CYAN)── Archivos modificados ──$(C_RESET)\n"
	@git status --short
	@echo ""

pre-demo: test awx-status  ## Checklist pre-demo: validate + awx-status
	@printf "$(C_GREEN)══════════════════════════════════════════════════════════════════$(C_RESET)\n"
	@printf "$(C_GREEN) Pre-demo check completo. Si todo OK, lanza con:$(C_RESET)\n"
	@printf "$(C_GREEN)   make demo       (real)$(C_RESET)\n"
	@printf "$(C_GREEN)   make mock       (eventos pregrabados, sin tocar nada)$(C_RESET)\n"
	@printf "$(C_GREEN)══════════════════════════════════════════════════════════════════$(C_RESET)\n"

# ─────────────────────────────────────────────────────────────────────────────
# Perfiles de entorno: alternar entre AWX local (192.168.250.20) y AWX Azure
# (172.210.65.202) sin editar codigo. Cada perfil tiene su set de JT IDs +
# AWX_URL + AWX_TOKEN. El target activa el perfil copiandolo a .env y luego
# levanta la webapp con `make demo`.
# ─────────────────────────────────────────────────────────────────────────────

profile-show:  ## Muestra el AWX_URL activo del .env actual
	@if [ -f .env ]; then \
		AWX=$$(grep -E "^AWX_URL=" .env | cut -d= -f2); \
		if echo "$$AWX" | grep -q "172.210.65.202"; then \
			printf "$(C_CYAN)Perfil activo:$(C_RESET) $(C_GREEN)AZURE$(C_RESET) ($$AWX)\n"; \
		elif echo "$$AWX" | grep -q "192.168.250.20"; then \
			printf "$(C_CYAN)Perfil activo:$(C_RESET) $(C_YELLOW)LOCAL$(C_RESET) ($$AWX)\n"; \
		else \
			printf "$(C_CYAN)Perfil activo:$(C_RESET) custom ($$AWX)\n"; \
		fi; \
	else \
		printf "$(C_RED)No hay .env. Crea uno desde .env.local.example o .env.azure.example$(C_RESET)\n"; \
	fi

profile-local:  ## Activa perfil LOCAL: copia .env.local a .env (NO levanta la app)
	@if [ ! -f .env.local ]; then \
		printf "$(C_RED).env.local no existe. Crealo: cp .env.local.example .env.local && editar$(C_RESET)\n"; \
		exit 1; \
	fi
	@cp .env.local .env
	@chmod 600 .env
	@printf "$(C_GREEN)✓ Perfil LOCAL activado$(C_RESET) (AWX 192.168.250.20)\n"

profile-azure:  ## Activa perfil AZURE: copia .env.azure a .env (NO levanta la app)
	@if [ ! -f .env.azure ]; then \
		printf "$(C_RED).env.azure no existe. Crealo: cp .env.azure.example .env.azure && editar$(C_RESET)\n"; \
		exit 1; \
	fi
	@cp .env.azure .env
	@chmod 600 .env
	@printf "$(C_GREEN)✓ Perfil AZURE activado$(C_RESET) (AWX 172.210.65.202)\n"

demo-local: profile-local demo  ## Activa perfil LOCAL y levanta dashboard

demo-azure: profile-azure demo  ## Activa perfil AZURE y levanta dashboard
