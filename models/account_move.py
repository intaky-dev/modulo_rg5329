from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    rg5329_perception_amount = fields.Monetary(
        string='Total Percepción RG 5329',
        compute='_compute_rg5329_perception',
        store=True
    )

    rg5329_base_amount = fields.Monetary(
        string='Base RG 5329',
        compute='_compute_rg5329_perception',
        store=True
    )

    @api.depends(
        'invoice_line_ids',
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.tax_ids',
        'amount_untaxed',
        'invoice_line_ids.product_id'
    )
    def _compute_rg5329_perception(self):
        for move in self:
            if move.move_type not in ['out_invoice', 'out_refund'] or move.partner_id.rg5329_exempt:
                move.rg5329_perception_amount = 0
                move.rg5329_base_amount = 0
                continue

            # Verificar categoría fiscal del cliente (solo Responsables Inscriptos)
            if not move._is_customer_eligible_for_rg5329():
                move.rg5329_perception_amount = 0
                move.rg5329_base_amount = 0
                continue

            # Aplicar automáticamente impuestos RG 5329 si corresponde
            move._auto_apply_rg5329_taxes()

            base_amount = 0
            perception_amount = 0

            # Calcular base imponible para productos RG 5329
            for line in move.invoice_line_ids:
                if line.product_id and line.product_id.apply_rg5329:
                    base_amount += line.price_subtotal

            move.rg5329_base_amount = base_amount

            # NORMATIVA: Mínimo sobre TOTAL de factura ($100,000 desde actualización)
            total_invoice = move.amount_untaxed or 0
            if total_invoice >= 100000 and base_amount > 0:
                for line in move.invoice_line_ids:
                    if line.product_id and line.product_id.apply_rg5329:
                        # Determinar alícuota según IVA del producto
                        iva_rate = move._get_line_iva_rate(line)
                        if iva_rate == 21.0:
                            perception_rate = 3.0  # 3%
                        elif iva_rate == 10.5:
                            perception_rate = 1.5  # 1,5%
                        else:
                            # FALLBACK: Si no detectamos IVA específico, aplicar 3% por defecto
                            # Esto maneja casos con BD limpias sin estructura fiscal argentina
                            perception_rate = 3.0
                            _logger.info("RG 5329: Aplicando 3%% por defecto para producto %s (IVA no detectado: %s)",
                                       line.product_id.name, iva_rate)

                        if perception_rate > 0:
                            line_perception = line.price_subtotal * (perception_rate / 100)
                            perception_amount += line_perception

            move.rg5329_perception_amount = perception_amount

    def _is_customer_eligible_for_rg5329(self):
        """
        Verifica si el cliente es elegible para RG 5329 según normativa AFIP
        Solo aplica a Responsables Inscriptos en IVA
        Robusto para entornos de producción y testing
        """
        try:
            partner = self.partner_id

            # Verificar si existe el campo de responsabilidad fiscal (compatibilidad)
            if not hasattr(partner, 'l10n_ar_afip_responsibility_type_id'):
                _logger.warning(
                    "Campo l10n_ar_afip_responsibility_type_id no encontrado "
                    "en partner %s. Asumiendo NO elegible para RG 5329 "
                    "(BD sin localización argentina completa).",
                    partner.name
                )
                # FIXED: Si no hay localización argentina, asumir NO elegible por defecto
                return False

            # Verificar si tiene responsabilidad fiscal configurada
            if not partner.l10n_ar_afip_responsibility_type_id:
                _logger.info(
                    "Partner %s sin responsabilidad fiscal configurada, "
                    "asumiendo NO elegible para RG 5329",
                    partner.name
                )
                # FIXED: Si no está configurado, asumir NO elegible por defecto
                return False

            # Solo aplicar a Responsables Inscriptos (código IVA_RI)
            responsibility_code = partner.l10n_ar_afip_responsibility_type_id.code

            # Códigos válidos para RG 5329 según normativa ARCA
            valid_codes = ['1']  # Solo código 1: IVA Responsable Inscripto

            is_eligible = responsibility_code in valid_codes

            if not is_eligible:
                _logger.debug("Partner %s con código %s no elegible para RG 5329",
                            partner.name, responsibility_code)

            return is_eligible

        except AttributeError as e:
            _logger.warning(
                "Error accediendo a campos AFIP en partner %s: %s. "
                "Asumiendo NO elegible para RG 5329.",
                self.partner_id.name if self.partner_id else 'Unknown',
                str(e)
            )
            return False  # FIXED: Asumir NO elegible en caso de error
        except Exception as e:
            _logger.error(
                "Error inesperado verificando elegibilidad RG 5329 "
                "para partner %s: %s. Asumiendo NO elegible.",
                self.partner_id.name if self.partner_id else 'Unknown',
                str(e)
            )
            return False  # FIXED: Asumir NO elegible en caso de error

    def _get_line_iva_rate(self, line):
        """Obtiene la alícuota de IVA de una línea"""
        for tax in line.tax_ids:
            if tax.type_tax_use == 'sale' and tax.amount in [21.0, 10.5]:
                return tax.amount
        return 0.0

    def _auto_apply_rg5329_taxes(self):
        """Aplica automáticamente los impuestos RG 5329 según normativa AFIP"""
        # Verificar si el cliente está exento
        if self.partner_id.rg5329_exempt:
            # Remover cualquier impuesto RG 5329 existente para clientes exentos
            for line in self.invoice_line_ids:
                rg5329_taxes = line.tax_ids.filtered('is_rg5329_perception')
                if rg5329_taxes:
                    for tax in rg5329_taxes:
                        line.tax_ids = [(3, tax.id)]
            return

        # Verificar categoría fiscal del cliente
        if not self._is_customer_eligible_for_rg5329():
            # Remover impuestos RG 5329 si no es elegible
            for line in self.invoice_line_ids:
                rg5329_taxes = line.tax_ids.filtered('is_rg5329_perception')
                if rg5329_taxes:
                    for tax in rg5329_taxes:
                        line.tax_ids = [(3, tax.id)]
            return

        # Buscar impuestos RG 5329 de forma más precisa para Odoo 18
        try:
            tax_3_percent = self.env['account.tax'].search([
                ('is_rg5329_perception', '=', True),
                ('amount', '=', 3.0),
                ('type_tax_use', '=', 'sale')
            ], limit=1)

            tax_1_5_percent = self.env['account.tax'].search([
                ('is_rg5329_perception', '=', True),
                ('amount', '=', 1.5),
                ('type_tax_use', '=', 'sale')
            ], limit=1)

            if not tax_3_percent or not tax_1_5_percent:
                _logger.warning("Impuestos RG 5329 no encontrados. "
                              "3%%: %s, 1.5%%: %s", bool(tax_3_percent), bool(tax_1_5_percent))
                return

        except Exception as e:
            _logger.error("Error buscando impuestos RG 5329: %s", str(e))
            return

        # NORMATIVA: Verificar mínimo sobre TOTAL de factura
        total_invoice = self.amount_untaxed or 0

        for line in self.invoice_line_ids:
            if line.product_id and line.product_id.apply_rg5329:
                # Determinar qué impuesto aplicar según IVA
                iva_rate = self._get_line_iva_rate(line)
                target_tax = None

                if iva_rate == 21.0 and tax_3_percent:
                    target_tax = tax_3_percent
                elif iva_rate == 10.5 and tax_1_5_percent:
                    target_tax = tax_1_5_percent
                else:
                    # FALLBACK: Si no detectamos IVA específico, usar 3% por defecto
                    # Esto maneja casos con BD limpias sin estructura fiscal argentina
                    target_tax = tax_3_percent
                    _logger.info("RG 5329: Aplicando impuesto 3%% por defecto para producto %s (IVA no detectado: %s)",
                               line.product_id.name, iva_rate)

                if target_tax:
                    # NORMATIVA: Solo aplicar si factura total >= $100,000
                    if total_invoice >= 100000:
                        # Agregar el impuesto si no está ya presente
                        if target_tax not in line.tax_ids:
                            line.tax_ids = [(4, target_tax.id)]
                    else:
                        # Remover el impuesto si no cumple el mínimo
                        if target_tax in line.tax_ids:
                            line.tax_ids = [(3, target_tax.id)]