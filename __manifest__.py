{
    "name": "AFIP RG 5329 - Percepción IVA Simplificado",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations/Argentina",
    "summary": "Régimen de percepción de IVA RG 5329 - Versión Simplificada - Odoo 18",
    "description": """
        Módulo para aplicar el régimen de percepción de IVA establecido por la RG 5329/2023.
        
        Compatibilidad: Odoo 18.0+
        
        Características:
        - Percepción 3% para productos con IVA 21%
        - Percepción 1,5% para productos con IVA 10,5%
        - Configuración simple en productos para activar cálculo
        - Mínimo de $100,000 en el total de compra
        - Cálculo automático según alícuota de IVA
        - Creación automática de cuenta contable 2.1.3.03.041
        - Exención por cliente
        - Tax group para visualización clara en facturas
    """,
    "author": "Tu Empresa",
    "website": "https://www.tuempresa.com",
    "license": "LGPL-3",
    "depends": [
        "account",
        "sale",
        "product",
        "l10n_ar",
        "point_of_sale",
    ],
    "external_dependencies": {
        "python": [],
    },
    # Odoo 18 específico
    "odoo_version": "18.0",
    "python_requires": ">=3.8",
    "data": [
        "security/ir.model.access.csv",
        "data/tax_data.xml",
        "views/product_template_views.xml",
        "views/res_partner_views.xml",
        "views/account_tax_views.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "modulo_rg5329/static/src/js/rg5329_auto_trigger.js",
        ],
        "point_of_sale._assets_pos": [
            "modulo_rg5329/static/src/js/pos_rg5329.js",
        ],
    },
    # Demo data created programmatically via installation script
    "installable": True,
    "auto_install": False,
    "application": True,
}
