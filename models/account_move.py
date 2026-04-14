import time

from odoo import models, fields, api, _
import logging

from ..utils import telemetry as otel

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
        _t0 = time.monotonic()
        for move in self:
            with otel.start_span("rg5329.invoice.compute_perception") as span:
                span.set_attribute("move.id", move.id or 0)
                span.set_attribute("move.type", move.move_type or "")
                span.set_attribute("partner.id", move.partner_id.id if move.partner_id else 0)
                try:
                    if move.move_type not in ['out_invoice', 'out_refund'] or move.partner_id.rg5329_exempt:
                        move.rg5329_perception_amount = 0
                        move.rg5329_base_amount = 0
                        span.set_attribute("skipped", True)
                        span.set_attribute("skip_reason", "wrong_type_or_exempt")
                        continue

                    # Verificar categoría fiscal del cliente (solo Responsables Inscriptos)
                    if not move._is_customer_eligible_for_rg5329():
                        move.rg5329_perception_amount = 0
                        move.rg5329_base_amount = 0
                        span.set_attribute("skipped", True)
                        span.set_attribute("skip_reason", "not_eligible")
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
                    span.set_attribute("invoice.total_untaxed", float(total_invoice))
                    span.set_attribute("invoice.base_amount", float(base_amount))

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
                                    perception_rate = 3.0
                                    _logger.info("RG 5329: Aplicando 3%% por defecto para producto %s (IVA no detectado: %s)",
                                               line.product_id.name, iva_rate)

                                if perception_rate > 0:
                                    line_perception = line.price_subtotal * (perception_rate / 100)
                                    perception_amount += line_perception

                    move.rg5329_perception_amount = perception_amount
                    span.set_attribute("perception_amount", float(perception_amount))

                except Exception as e:
                    span.record_exception(e)
                    otel.record_error("AccountMove._compute_rg5329_perception")
                    raise

        otel.record_processing_duration(
            (time.monotonic() - _t0) * 1000,
            order_type="invoice",
        )

    def _is_customer_eligible_for_rg5329(self):
        """
        Verifica si el cliente es elegible para RG 5329 según normativa AFIP
        Solo aplica a Responsables Inscriptos en IVA
        Robusto para entornos de producción y testing
        """
        with otel.start_span("rg5329.invoice.eligibility_check") as span:
            span.set_attribute("partner.id", self.partner_id.id if self.partner_id else 0)
            span.set_attribute("partner.name", self.partner_id.name or "")
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
                    span.set_attribute("eligible", False)
                    span.set_attribute("skip_reason", "no_afip_field")
                    return False

                # Verificar si tiene responsabilidad fiscal configurada
                if not partner.l10n_ar_afip_responsibility_type_id:
                    _logger.debug(
                        "Partner %s sin responsabilidad fiscal configurada, "
                        "asumiendo NO elegible para RG 5329",
                        partner.name
                    )
                    span.set_attribute("eligible", False)
                    span.set_attribute("skip_reason", "no_responsibility_configured")
                    return False

                # Solo aplicar a Responsables Inscriptos (código IVA_RI)
                responsibility_code = partner.l10n_ar_afip_responsibility_type_id.code
                is_eligible = responsibility_code == '1'

                span.set_attribute("partner.afip_code", responsibility_code or "")
                span.set_attribute("eligible", is_eligible)

                if not is_eligible:
                    _logger.debug("Partner %s con código %s no elegible para RG 5329",
                                partner.name, responsibility_code)

                return is_eligible

            except Exception as e:
                span.record_exception(e)
                otel.record_error("AccountMove._is_customer_eligible_for_rg5329")
                _logger.error(
                    "Error inesperado verificando elegibilidad RG 5329 "
                    "para partner %s: %s. Asumiendo NO elegible.",
                    self.partner_id.name if self.partner_id else 'Unknown',
                    str(e)
                )
                return False

    def _get_line_iva_rate(self, line):
        """Obtiene la alícuota de IVA de una línea"""
        for tax in line.tax_ids:
            if tax.type_tax_use == 'sale' and tax.amount in [21.0, 10.5]:
                return tax.amount
        return 0.0

    def _auto_apply_rg5329_taxes(self):
        """Aplica automáticamente los impuestos RG 5329 según normativa AFIP"""
        with otel.start_span("rg5329.invoice.auto_apply_taxes") as span:
            span.set_attribute("move.id", self.id or 0)
            span.set_attribute("move.type", self.move_type or "")
            span.set_attribute("partner.id", self.partner_id.id if self.partner_id else 0)
            try:
                # Verificar si el cliente está exento
                if self.partner_id.rg5329_exempt:
                    # Remover cualquier impuesto RG 5329 existente para clientes exentos
                    for line in self.invoice_line_ids:
                        rg5329_taxes = line.tax_ids.filtered('is_rg5329_perception')
                        if rg5329_taxes:
                            for tax in rg5329_taxes:
                                line.tax_ids = [(3, tax.id)]
                    otel.record_perception_skipped(order_type="invoice", reason="customer_exempt")
                    return

                # Verificar categoría fiscal del cliente
                if not self._is_customer_eligible_for_rg5329():
                    # Remover impuestos RG 5329 si no es elegible
                    for line in self.invoice_line_ids:
                        rg5329_taxes = line.tax_ids.filtered('is_rg5329_perception')
                        if rg5329_taxes:
                            for tax in rg5329_taxes:
                                line.tax_ids = [(3, tax.id)]
                    otel.record_perception_skipped(order_type="invoice", reason="not_eligible")
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
                        otel.record_perception_skipped(order_type="invoice", reason="no_tax_found")
                        return

                except Exception as e:
                    span.record_exception(e)
                    otel.record_error("AccountMove._auto_apply_rg5329_taxes")
                    _logger.error("Error buscando impuestos RG 5329: %s", str(e))
                    return

                # NORMATIVA: Verificar mínimo sobre TOTAL de factura
                total_invoice = self.amount_untaxed or 0
                span.set_attribute("invoice.total_untaxed", float(total_invoice))

                for line in self.invoice_line_ids:
                    if line.product_id and line.product_id.apply_rg5329:
                        # Determinar qué impuesto aplicar según IVA
                        iva_rate = self._get_line_iva_rate(line)
                        target_tax = None

                        if iva_rate == 21.0 and tax_3_percent:
                            target_tax = tax_3_percent
                            perception_rate = 3.0
                        elif iva_rate == 10.5 and tax_1_5_percent:
                            target_tax = tax_1_5_percent
                            perception_rate = 1.5
                        else:
                            # FALLBACK: Si no detectamos IVA específico, usar 3% por defecto
                            # Esto maneja casos con BD limpias sin estructura fiscal argentina
                            target_tax = tax_3_percent
                            perception_rate = 3.0
                            _logger.info("RG 5329: Aplicando impuesto 3%% por defecto para producto %s (IVA no detectado: %s)",
                                       line.product_id.name, iva_rate)

                        if target_tax:
                            # NORMATIVA: Solo aplicar si factura total >= $10.000.000 (RG 5329)
                            if total_invoice >= 10000000:
                                # Agregar el impuesto si no está ya presente
                                if target_tax not in line.tax_ids:
                                    line.tax_ids = [(4, target_tax.id)]
                                    otel.record_perception_applied(
                                        order_type="invoice",
                                        rate=perception_rate,
                                        base_amount=float(line.price_subtotal),
                                    )
                            else:
                                # Remover el impuesto si no cumple el mínimo
                                if target_tax in line.tax_ids:
                                    line.tax_ids = [(3, target_tax.id)]
                                    otel.record_perception_skipped(
                                        order_type="invoice",
                                        reason="below_threshold",
                                    )
            except Exception as e:
                span.record_exception(e)
                otel.record_error("AccountMove._auto_apply_rg5329_taxes")
                raise

    def wsfe_get_cae_request(self, client=None):
        """Override para inyectar CondicionIVAReceptorId requerido por RG 5616."""
        with otel.start_span("rg5329.invoice.wsfe_cae_request") as span:
            span.set_attribute("move.id", self.id or 0)
            span.set_attribute("move.name", self.name or "")
            span.set_attribute("move.type", self.move_type or "")
            span.set_attribute("partner.id", self.commercial_partner_id.id if self.commercial_partner_id else 0)
            try:
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
                span.set_attribute("condicion_iva", condicion_iva)
                otel.record_cae_enrichment(condicion_iva)
                return res
            except Exception as e:
                span.record_exception(e)
                otel.record_error("AccountMove.wsfe_get_cae_request")
                raise
