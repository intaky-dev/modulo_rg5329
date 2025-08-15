{
    "name": "AFIP RG 5329 - Percepción IVA Simplificado",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations/Argentina",
    "summary": "Régimen de percepción de IVA RG 5329 - Versión Simplificada",
    "description": """
        Módulo simplificado para aplicar el régimen de percepción de IVA 
        establecido por la RG 5329/2023.
        
        Características:
        - Percepción 3% para productos con IVA 21%
        - Percepción 1,5% para productos con IVA 10,5%
        - Boolean simple en productos para activar cálculo
        - Mínimo de $100.000 en el total de compra
        - Cálculo automático según alícuota de IVA
    """,
    "author": "Tu Empresa",
    "website": "https://www.tuempresa.com",
    "license": "LGPL-3",
    "depends": [
        "account",
        "sale",
        "product",
        "l10n_ar",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/tax_data.xml",
        "views/res_partner_views.xml",
        "views/account_tax_views.xml",
        "views/account_move_views.xml"
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
