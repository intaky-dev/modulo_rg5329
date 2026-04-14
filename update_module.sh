#!/bin/bash
# Actualiza modulo_rg5329 en el servidor Odoo
# Uso: ./update_module.sh

set -euo pipefail

MODULE_SOURCE_PATH="/usr/lib/python3/dist-packages/odoo/addons/modulo_rg5329"

ssh odoo@10.5.0.41 bash -s << EOF
set -euo pipefail

cd $MODULE_SOURCE_PATH

echo "==> git pull..."
git pull

echo "==> Deteniendo Odoo..."
sudo systemctl stop odoo

echo "==> Actualizando módulo..."
odoo -c /etc/odoo/odoo.conf \
    -u modulo_rg5329 \
    --stop-after-init

echo "==> Iniciando Odoo..."
sudo systemctl start odoo

echo "==> Listo."
EOF
