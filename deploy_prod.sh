#!/bin/bash
set -euo pipefail

# ==============================================
# CONFIGURACIÓN - Completar antes de ejecutar
# ==============================================
PROD_USER="PROD_USER"          # ej: ubuntu, odoo, deploy
PROD_HOST="PROD_HOST"          # ej: 192.168.1.100 o mi-servidor.com
MODULE_NAME="modulo_rg5329"
REMOTE_ADDONS="/usr/lib/python3/dist-packages/odoo/addons"
ODOO_SERVICE="odoo"
DB_NAME="odoo"
ODOO_BIN="/usr/bin/odoo-bin"
ODOO_SYSTEM_USER="odoo"
LOCAL_MODULE_PATH="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$LOCAL_MODULE_PATH/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ==============================================
# HELPERS
# ==============================================
log()   { echo "[$(date '+%H:%M:%S')] $*"; }
error() { echo "[ERROR] $*" >&2; exit 1; }
confirm() {
    read -r -p "$1 [s/N]: " resp
    [[ "$resp" =~ ^[sS]$ ]] || error "Cancelado por el usuario."
}

# ==============================================
# VALIDACIONES PREVIAS
# ==============================================
log "=== Deploy $MODULE_NAME → Producción ==="
log "Destino : $PROD_USER@$PROD_HOST"
log "Addons  : $REMOTE_ADDONS"
log "Servicio: $ODOO_SERVICE  |  DB: $DB_NAME"

if [[ "$PROD_USER" == "PROD_USER" || "$PROD_HOST" == "PROD_HOST" ]]; then
    error "Configurar PROD_USER y PROD_HOST antes de ejecutar este script."
fi

log "Verificando acceso SSH..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "$PROD_USER@$PROD_HOST" "echo OK" \
    || error "Sin acceso SSH a $PROD_USER@$PROD_HOST. Verificar clave y host."

confirm "Continuar con el deploy a produccion?"

# ==============================================
# STEP 1: BACKUP
# ==============================================
log ""
log "--- STEP 1: Backup de base de datos ---"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/backup_${DB_NAME}_${TIMESTAMP}.sql.gz"
log "Generando backup → $BACKUP_FILE"
ssh "$PROD_USER@$PROD_HOST" \
    "sudo -u postgres pg_dump $DB_NAME | gzip" > "$BACKUP_FILE"
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log "Backup OK ($BACKUP_SIZE) → $BACKUP_FILE"

# ==============================================
# STEP 2: SYNC MÓDULO
# ==============================================
log ""
log "--- STEP 2: Sincronizar módulo al servidor ---"
rsync -avz --delete \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='backups/' \
    --exclude='*.sh' \
    --exclude='*.md' \
    --exclude='.openviking/' \
    --exclude='my_module/' \
    "$LOCAL_MODULE_PATH/" \
    "$PROD_USER@$PROD_HOST:/tmp/${MODULE_NAME}_deploy/"

# Mover con sudo al path de addons y corregir permisos
ssh "$PROD_USER@$PROD_HOST" "
    sudo cp -r /tmp/${MODULE_NAME}_deploy/ $REMOTE_ADDONS/$MODULE_NAME
    sudo chown -R $ODOO_SYSTEM_USER:$ODOO_SYSTEM_USER $REMOTE_ADDONS/$MODULE_NAME
    rm -rf /tmp/${MODULE_NAME}_deploy/
    echo 'Sync OK'
"

# ==============================================
# STEP 3: UPGRADE
# ==============================================
log ""
log "--- STEP 3: Upgrade del módulo ---"
log "Deteniendo servicio Odoo..."
ssh "$PROD_USER@$PROD_HOST" "sudo systemctl stop $ODOO_SERVICE"

log "Ejecutando upgrade (puede tardar unos minutos)..."
UPGRADE_OUTPUT=$(ssh "$PROD_USER@$PROD_HOST" \
    "sudo -u $ODOO_SYSTEM_USER $ODOO_BIN \
        -u $MODULE_NAME \
        -d $DB_NAME \
        --stop-after-init \
        --no-http \
        2>&1" || true)

# Detectar errores críticos en el output del upgrade
if echo "$UPGRADE_OUTPUT" | grep -qiE "^[0-9-]+ [0-9:]+ [0-9]+ (ERROR|CRITICAL)"; then
    log ""
    log "=== OUTPUT DEL UPGRADE (últimas 60 líneas) ==="
    echo "$UPGRADE_OUTPUT" | tail -60
    log ""
    log "Reiniciando Odoo con el código anterior..."
    ssh "$PROD_USER@$PROD_HOST" "sudo systemctl start $ODOO_SERVICE" || true
    error "El upgrade reportó errores. Odoo reiniciado. Backup disponible en: $BACKUP_FILE"
fi

log "Upgrade completado sin errores críticos."
log "Iniciando servicio Odoo..."
ssh "$PROD_USER@$PROD_HOST" "sudo systemctl start $ODOO_SERVICE"

# Esperar que Odoo levante (max 60s)
log "Esperando respuesta HTTP de Odoo..."
for i in $(seq 1 30); do
    STATUS=$(ssh "$PROD_USER@$PROD_HOST" \
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:8069/web/health 2>/dev/null" || echo "000")
    if [[ "$STATUS" == "200" ]]; then
        log "Odoo respondiendo OK (HTTP 200)"
        break
    fi
    if [[ "$i" -eq 30 ]]; then
        log ""
        log "Odoo no respondio en 60s. Ver logs con:"
        log "  ssh $PROD_USER@$PROD_HOST 'sudo journalctl -u $ODOO_SERVICE -n 50'"
        error "Timeout esperando Odoo. Verificar manualmente."
    fi
    sleep 2
done

# ==============================================
# STEP 4: TESTS POST-UPGRADE
# ==============================================
log ""
log "--- STEP 4: Tests post-upgrade ---"
TEST_SCRIPT="$(dirname "$0")/test_upgrade.py"
if [[ -f "$TEST_SCRIPT" ]] && command -v python3 &>/dev/null; then
    python3 "$TEST_SCRIPT" \
        --host "http://$PROD_HOST:8069" \
        --db "$DB_NAME" \
        && log "Tests OK" \
        || { log "Algunos tests fallaron. Ver salida arriba."; TESTS_FAILED=1; }
else
    log "python3 o test_upgrade.py no disponibles, saltando tests automaticos"
fi

# ==============================================
# RESUMEN
# ==============================================
log ""
log "================================================"
log "DEPLOY COMPLETADO"
log "  Backup : $BACKUP_FILE ($BACKUP_SIZE)"
log "  Odoo   : http://$PROD_HOST:8069"
if [[ "${TESTS_FAILED:-0}" == "1" ]]; then
    log "  Tests  : ALGUNOS FALLARON - revisar manualmente"
else
    log "  Tests  : OK"
fi
log "================================================"
