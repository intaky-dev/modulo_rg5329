from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AccountSetup(models.TransientModel):
    _name = 'rg5329.account.setup'
    _description = 'RG 5329 Account Setup'

    @api.model
    def setup_rg5329_accounts(self):
        """
        Crea automáticamente la cuenta de percepciones RG 5329 si no existe
        y la asigna a los impuestos RG 5329
        """
        AccountAccount = self.env['account.account']
        AccountTax = self.env['account.tax']

        # Código de cuenta estándar argentino para percepciones IVA
        account_code = '2.1.3.03.041'
        account_name = 'Percepciones de IVA RG 5329'

        # Verificar si la cuenta ya existe
        existing_account = AccountAccount.search([
            ('code', '=', account_code)
        ], limit=1)

        if existing_account:
            perception_account = existing_account
            _logger.info(f"✅ Cuenta {account_code} ya existe, usando existente")
        else:
            # Crear la cuenta si no existe
            try:
                perception_account = AccountAccount.create({
                    'code': account_code,
                    'name': account_name,
                    'account_type': 'liability_current',
                    'reconcile': True,
                })
                _logger.info(f"✅ Cuenta {account_code} creada exitosamente")
            except Exception as e:
                _logger.error(f"⚠️ Error creando cuenta {account_code}: {e}")
                return False

        # Buscar los impuestos RG 5329 creados por el módulo
        rg5329_taxes = AccountTax.search([
            ('is_rg5329_perception', '=', True)
        ])

        if not rg5329_taxes:
            _logger.warning("⚠️ No se encontraron impuestos RG 5329")
            return False

        # Asignar la cuenta a los impuestos RG 5329
        for tax in rg5329_taxes:
            try:
                # Método simplificado para Odoo 18
                # Solo asignar si el impuesto no tiene cuenta ya configurada

                # Verificar si ya tiene líneas de distribución con cuenta
                tax_lines_with_account = tax.invoice_repartition_line_ids.filtered(
                    lambda l: l.repartition_type == 'tax' and l.account_id
                )

                if not tax_lines_with_account:
                    # Buscar líneas de tax sin cuenta y asignarlas
                    tax_lines = tax.invoice_repartition_line_ids.filtered(
                        lambda l: l.repartition_type == 'tax'
                    )
                    if tax_lines:
                        tax_lines.write({'account_id': perception_account.id})
                        _logger.info(f"✅ Cuenta asignada a impuesto {tax.name}")
                    else:
                        _logger.warning(f"⚠️ No se encontraron líneas de distribución para {tax.name}")
                else:
                    _logger.info(f"ℹ️ Impuesto {tax.name} ya tiene cuenta configurada")

            except Exception as e:
                _logger.error(f"⚠️ Error con impuesto {tax.name}: {e}")
                # Continuar con el siguiente impuesto
                continue

        _logger.info("🎉 Configuración de cuentas RG 5329 completada")
        return True
