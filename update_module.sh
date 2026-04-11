#!/bin/bash
# Actualiza modulo_rg5329 en el servidor Odoo
# Uso: ./update_module.sh <base_de_datos>

set -euo pipefail

DB="${1:?Uso: $0 <base_de_datos>}"

ssh odoo@10.5.0.41 bash -s << EOF
set -euo pipefail

cd /usr/lib/python3/dist-packages/odoo/addons/modulo_rg5329

echo "==> git pull..."
git pull

echo "==> Deteniendo Odoo..."
sudo systemctl stop odoo

echo "==> Actualizando módulo..."
odoo -c /etc/odoo/odoo.conf \
    -u modulo_rg5329 \
    -d $DB \
    --stop-after-init \
    --no-http

echo "==> Iniciando Odoo..."
sudo systemctl start odoo

echo "==> Listo."
EOF
