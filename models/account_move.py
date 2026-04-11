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
            if move.move_type not in ['out_invoice', 'out_refund'] or not move.partner_id._is_rg5329_eligible():
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

            # NORMATIVA: Mínimo sobre TOTAL de factura ($10.000.000 según RG 5329)
            total_invoice = move.amount_untaxed or 0
            if total_invoice >= 10000000 and base_amount > 0:
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

    def _get_line_iva_rate(self, line):
        """Obtiene la alícuota de IVA de una línea"""
        for tax in line.tax_ids:
            if tax.type_tax_use == 'sale' and tax.amount in [21.0, 10.5]:
                return tax.amount
        return 0.0

    def _auto_apply_rg5329_taxes(self):
        """Aplica automáticamente los impuestos RG 5329 según normativa AFIP"""
        # Remover impuestos si el partner no es elegible (exento o no Responsable Inscripto)
        if not self.partner_id._is_rg5329_eligible():
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
                    # NORMATIVA: Solo aplicar si factura total >= $10.000.000 (RG 5329)
                    if total_invoice >= 10000000:
                        # Agregar el impuesto si no está ya presente
                        if target_tax not in line.tax_ids:
                            line.tax_ids = [(4, target_tax.id)]
                    else:
                        # Remover el impuesto si no cumple el mínimo
                        if target_tax in line.tax_ids:
                            line.tax_ids = [(3, target_tax.id)]

    def wsfe_get_cae_request(self, client=None):
        """Override para inyectar CondicionIVAReceptorId requerido por RG 5616."""
        res = super().wsfe_get_cae_request(client=client)
        partner = self.commercial_partner_id
        responsibility = partner.l10n_ar_afip_responsibility_type_id
        condicion_iva = 5  # Consumidor Final como fallback
        if responsibility and responsibility.code:
            try:
                condicion_iva = int(responsibility.code)
            except (ValueError, TypeError):
                pass
        res['FeDetReq'][0]['FECAEDetRequest']['CondicionIVAReceptorId'] = condicion_iva
        return res
