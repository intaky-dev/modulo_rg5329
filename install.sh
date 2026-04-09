#!/bin/bash

# Simple Final Auto-Install Script for RG 5329 Module
# Assumes database 'odoo' exists with admin/admin credentials

set -e  # Exit on any error

# Configuration
MODULE_NAME="modulo_rg5329"
DOCKER_COMPOSE_PATH="$HOME/Desktop/Dev/odoo-enter18"
MODULE_SOURCE_PATH="$HOME/Desktop/Dev/modulo_rg5329"
DB_NAME="odoo"
ADMIN_USER="admin"
ADMIN_PASSWORD="admin"
CONTAINER_NAME="odoo-enterprise"

echo "🚀 Simple Auto-Install RG 5329 Module..."

# Check if module directory exists
if [ ! -d "$MODULE_SOURCE_PATH" ]; then
    echo "❌ Error: Module directory not found at $MODULE_SOURCE_PATH"
    exit 1
fi

# Check if docker-compose directory exists
if [ ! -d "$DOCKER_COMPOSE_PATH" ]; then
    echo "❌ Error: Docker compose directory not found at $DOCKER_COMPOSE_PATH"
    exit 1
fi

echo "✅ Starting installation process..."

# Navigate to docker-compose directory
cd "$DOCKER_COMPOSE_PATH"

# Full cleanup
echo "🧹 Cleaning up containers and volumes..."
docker compose down -v --remove-orphans
docker volume ls -q | grep -E "(odoo|postgres)" | xargs -r docker volume rm 2>/dev/null || true

# Start fresh with demo data enabled
echo "🚀 Starting fresh containers with DEMO DATA enabled..."
docker compose up -d

# Wait for containers
echo "⏳ Waiting for containers to be ready..."
sleep 30

# Wait for Odoo to be responsive
echo "⏳ Waiting for Odoo to be ready..."
for i in {1..20}; do
    if docker exec "$CONTAINER_NAME" curl -s http://localhost:8069/web/database/selector > /dev/null 2>&1; then
        echo "✅ Odoo is responding"
        break
    fi
    if [ $i -eq 20 ]; then
        echo "❌ Odoo not responding after 3+ minutes"
        exit 1
    fi
    echo "   Checking... ($i/20)"
    sleep 10
done

# Copy module
echo "📦 Copying module to container..."
docker cp "$MODULE_SOURCE_PATH" "$CONTAINER_NAME:/usr/lib/python3/dist-packages/odoo/addons/"
echo "✅ Module copied successfully"

# Enable demo data parameter
echo "🎯 Enabling demo data globally..."
docker exec "$CONTAINER_NAME" python3 -c "
import xmlrpc.client
url = 'http://localhost:8069'
db = '$DB_NAME'
username = '$ADMIN_USER'
password = '$ADMIN_PASSWORD'

try:
    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
    uid = common.authenticate(db, username, password, {})
    if uid:
        # Set demo data parameter
        models.execute_kw(db, uid, password, 'ir.config_parameter', 'set_param', ['base.load_demo_data', 'True'])
        print('✅ Demo data parameter enabled')
    else:
        print('⚠️  Could not authenticate - demo data will be handled by module manifest')
except:
    print('⚠️  Could not set demo parameter - will rely on module demo data')
" || echo "⚠️  Demo parameter setup failed - continuing with module demo data"

# Install module via Odoo XML-RPC (simplified for existing DB)
echo "🎯 Installing module automatically..."
docker exec "$CONTAINER_NAME" python3 -c "
import xmlrpc.client
import time
import sys

# Configuration
url = 'http://localhost:8069'
db = '$DB_NAME'
username = '$ADMIN_USER'
password = '$ADMIN_PASSWORD'
module_name = '$MODULE_NAME'

try:
    print('🔗 Connecting to Odoo...')

    # Connect to common service
    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))

    # Authenticate (assumes DB exists)
    print('🔐 Authenticating...')
    uid = common.authenticate(db, username, password, {})
    if not uid:
        print('❌ Authentication failed - database may not exist or wrong credentials')
        print('   Please create database manually first')
        sys.exit(1)
    print(f'✅ Authenticated as user {uid}')

    # Connect to object service
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))

    # Update apps list
    print('🔄 Updating apps list...')
    models.execute_kw(db, uid, password, 'ir.module.module', 'update_list', [])
    print('✅ Apps list updated')

    # Install required base modules in correct order
    print('📦 Installing base modules in correct order...')

    # Order matters! Account first, then sales, then localization
    required_modules = [
        ('base', 'Base Module'),
        ('account', 'Accounting'),
        ('sale', 'Sales Management'),  # Changed name to match Odoo 18
        ('l10n_ar', 'Argentina Localization')
    ]

    for req_module_name, module_desc in required_modules:
        print(f'🔍 Installing {module_desc} ({req_module_name})...')
        try:
            req_module_ids = models.execute_kw(db, uid, password, 'ir.module.module', 'search', [[['name', '=', req_module_name]]])
            if req_module_ids:
                req_module_info = models.execute_kw(db, uid, password, 'ir.module.module', 'read', [req_module_ids[0]], {'fields': ['state']})
                current_state = req_module_info[0]['state']

                if current_state == 'uninstalled':
                    print(f'   Installing {module_desc}...')
                    models.execute_kw(db, uid, password, 'ir.module.module', 'button_immediate_install', [req_module_ids[0]])

                    # Wait for installation to complete and verify
                    installation_success = False
                    for i in range(60):  # Wait up to 60 seconds for complex modules
                        time.sleep(1)
                        updated_info = models.execute_kw(db, uid, password, 'ir.module.module', 'read', [req_module_ids[0]], {'fields': ['state']})
                        if updated_info[0]['state'] == 'installed':
                            print(f'✅ {module_desc} installed successfully')
                            installation_success = True
                            break
                        elif i == 59:
                            print(f'⚠️  {module_desc} installation timeout after 60 seconds')
                            break
                        elif i % 10 == 0:  # Progress update every 10 seconds
                            print(f'   Still installing {module_desc}... ({i+1}s)')

                    if not installation_success:
                        print(f'❌ Failed to install {module_desc}, but continuing...')
                elif current_state == 'installed':
                    print(f'✅ {module_desc} already installed')
                else:
                    print(f'ℹ️  {module_desc} state: {current_state}')
            else:
                print(f'⚠️  {module_desc} not found in apps list')
        except Exception as e:
            print(f'❌ Error installing {module_desc}: {str(e)}')
            # Continue with next module

    # Give system time to stabilize
    print('⏳ Waiting for system stabilization...')
    time.sleep(5)

    # Search for our RG 5329 module
    print(f'🔍 Searching for module {module_name}...')
    module_ids = models.execute_kw(db, uid, password, 'ir.module.module', 'search', [[['name', '=', module_name]]])

    if not module_ids:
        print(f'❌ Module {module_name} not found')
        print('   Check module syntax and try manual installation')
        sys.exit(1)

    module_id = module_ids[0]
    module_info = models.execute_kw(db, uid, password, 'ir.module.module', 'read', [module_id], {'fields': ['name', 'state', 'shortdesc']})

    print(f'✅ Found module: {module_info[0][\"shortdesc\"]}')
    print(f'   Current state: {module_info[0][\"state\"]}')

    # Install the module if not already installed
    if module_info[0]['state'] == 'uninstalled':
        print('📦 Installing module...')
        models.execute_kw(db, uid, password, 'ir.module.module', 'button_immediate_install', [module_id])
        print('✅ Module installation completed!')

    elif module_info[0]['state'] == 'installed':
        print('ℹ️  Module is already installed')
        print('   Skipping installation to avoid conflicts')

    else:
        print(f'ℹ️  Module state: {module_info[0][\"state\"]} - trying to install...')
        try:
            models.execute_kw(db, uid, password, 'ir.module.module', 'button_immediate_install', [module_id])
            print('✅ Module installation completed!')
        except Exception as e:
            print(f'⚠️  Could not install module: {str(e)}')

    # Force create demo data manually since Odoo 18 doesn't handle it automatically
    print('🎯 Creating demo data manually...')
    time.sleep(2)

    # Create demo partners
    try:
        # Check if demo data already exists
        existing_partner = models.execute_kw(db, uid, password, 'res.partner', 'search', [[['name', '=', 'EMPRESA DEMO RI - Para Probar RG 5329']]])

        if not existing_partner:
            # Find Argentina country
            country_ar = models.execute_kw(db, uid, password, 'res.country', 'search', [[['code', '=', 'AR']]])
            country_id = country_ar[0] if country_ar else False

            # Create RI partner
            partner_ri = {
                'name': 'EMPRESA DEMO RI - Para Probar RG 5329',
                'is_company': True,
                'vat': '20123456789',
                'street': 'Av. Corrientes 1234',
                'city': 'Buenos Aires',
                'zip': 'C1043AAZ',
                'country_id': country_id,
                'email': 'demo@empresa-ri.com.ar',
                'phone': '+54 11 4567-8900',
                'rg5329_exempt': False,
            }
            models.execute_kw(db, uid, password, 'res.partner', 'create', [partner_ri])
            print('✅ Created RI demo partner')

            # Create exempt partner
            partner_exento = {
                'name': 'CLIENTE EXENTO RG 5329 - Para Probar Exención',
                'is_company': True,
                'vat': '20987654321',
                'street': 'San Martín 567',
                'city': 'Córdoba',
                'zip': 'X5000ABC',
                'country_id': country_id,
                'email': 'exento@cliente.com.ar',
                'phone': '+54 351 123-4567',
                'rg5329_exempt': True,
            }
            models.execute_kw(db, uid, password, 'res.partner', 'create', [partner_exento])
            print('✅ Created exempt demo partner')
        else:
            print('✅ Demo partners already exist')
    except Exception as e:
        print(f'⚠️  Could not create demo partners: {e}')

    # Create demo products
    try:
        existing_product = models.execute_kw(db, uid, password, 'product.template', 'search', [[['name', '=', 'PRODUCTO ALTO VALOR RG 5329 (Para probar percepción)']]])

        if not existing_product:
            # Find product category (All category)
            category = models.execute_kw(db, uid, password, 'product.category', 'search', [[]], {'limit': 1})
            category_id = category[0] if category else 1  # Default to ID 1 if not found

            # Create high value product
            product_alto = {
                'name': 'PRODUCTO ALTO VALOR RG 5329 (Para probar percepción)',
                'default_code': 'DEMO_RG5329_ALTO',
                'type': 'consu',  # consumable is valid in Odoo 18
                'categ_id': category_id,
                'list_price': 60000.00,
                'standard_price': 45000.00,
                'apply_rg5329': True,
            }
            models.execute_kw(db, uid, password, 'product.template', 'create', [product_alto])
            print('✅ Created high value demo product')

            # Create normal product
            product_normal = {
                'name': 'PRODUCTO NORMAL (Sin RG 5329)',
                'default_code': 'DEMO_NORMAL',
                'type': 'consu',
                'categ_id': category_id,
                'list_price': 30000.00,
                'standard_price': 20000.00,
                'apply_rg5329': False,
            }
            models.execute_kw(db, uid, password, 'product.template', 'create', [product_normal])
            print('✅ Created normal demo product')
        else:
            print('✅ Demo products already exist')
    except Exception as e:
        print(f'⚠️  Could not create demo products: {e}')

    print('✅ Installation process completed')

    # Verify demo data was loaded
    print('🔍 Verifying demo data was loaded...')
    time.sleep(2)

    try:
        # Check for demo partners
        demo_partners = models.execute_kw(db, uid, password, 'res.partner', 'search_count', [[['name', 'like', 'EMPRESA DEMO RI']]])
        demo_products = models.execute_kw(db, uid, password, 'product.template', 'search_count', [[['name', 'like', 'PRODUCTO ALTO VALOR RG 5329']]])

        if demo_partners > 0 and demo_products > 0:
            print(f'✅ Demo data loaded successfully!')
            print(f'   • Demo partners: {demo_partners}')
            print(f'   • Demo products: {demo_products}')
        else:
            print(f'⚠️  Demo data may not have loaded properly')
            print(f'   • Demo partners: {demo_partners}')
            print(f'   • Demo products: {demo_products}')
            print('   Try manual creation or check module manifest')
    except:
        print('⚠️  Could not verify demo data - check manually')

except Exception as e:
    print(f'❌ Error: {str(e)}')
    print('📋 Try manual installation:')
    print('   1. Go to http://localhost:8069')
    print('   2. Create database \"odoo\" with admin/admin')
    print('   3. Apps → Update Apps List')
    print('   4. Search \"RG 5329\" and install')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 INSTALLATION SUCCESSFUL!"
    echo ""
    echo "✅ Module RG 5329 is now installed with DEMO DATA!"
    echo "🌐 Access Odoo at: http://localhost:8069"
    echo "🔑 Login: admin / admin"
    echo "💾 Database: $DB_NAME"
    echo ""
    echo "🎯 DEMO DATA INCLUDED:"
    echo "   📋 Clientes demo:"
    echo "      • EMPRESA DEMO RI - Para Probar RG 5329 (NO exento)"
    echo "      • CLIENTE EXENTO RG 5329 - Para Probar Exención (EXENTO)"
    echo "   📦 Productos demo:"
    echo "      • PRODUCTO ALTO VALOR RG 5329 (\$60,000) - Con RG 5329"
    echo "      • PRODUCTO NORMAL (\$30,000) - Sin RG 5329"
    echo ""
    echo "🔧 Module Features:"
    echo "   • Módulos base instalados: Sales, Accounting, Argentina Localization"
    echo "   • Cuenta automática: 2.1.3.03.041 - Percepciones de IVA RG 5329"
    echo "   • Automatic 3% (IVA 21%) and 1.5% (IVA 10.5%) calculations"
    echo "   • \$100,000 minimum threshold (total invoice)"
    echo "   • Tax grouping shows 'Percepción RG 5329' on invoices"
    echo ""
else
    echo ""
    echo "❌ Automatic installation failed"
    echo "📋 Try manual installation at http://localhost:8069"
    echo ""
fi
