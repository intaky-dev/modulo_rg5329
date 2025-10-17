from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def apply_rg5329_logic_manual(self):
        """Public method to manually trigger RG5329 logic"""
        self._apply_rg5329_logic()
        return True

    def apply_rg5329_manual_button(self):
        """Manual button to apply RG5329 tax - Reliable UI method"""
        try:
            _logger.info("RG5329 BUTTON: Manual button clicked for purchase order %s", self.name)

            # Apply the logic
            self._apply_rg5329_logic()

            # Force UI refresh
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
            self._amount_all()

            # Show success message to user
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'RG5329 Tax Applied',
                    'message': f'RG5329 tax has been applied to purchase order {self.name}. New total: ${self.amount_total:,.2f}',
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error("RG5329 BUTTON: Error in manual button: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'RG5329 Error',
                    'message': f'Error applying RG5329 tax: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def button_confirm(self):
        """Override button_confirm to ensure RG5329 taxes are applied and preserved"""
        # STEP 1: Apply RG5329 logic one last time before confirming
        for order in self:
            if not self.env.context.get('skip_rg5329_confirm'):
                _logger.info("RG5329: Applying logic before confirming order %s (state: %s)", order.name, order.state)
                if order.state in ['draft', 'sent']:
                    order._apply_rg5329_logic()
                    order._amount_all()
                    _logger.info("RG5329: After applying logic - Total: %s, Tax: %s", order.amount_total, order.amount_tax)

                    # STEP 2: Store RG5329 tax info BEFORE confirmation to prevent loss
                    order._store_rg5329_taxes_before_confirm()

        # STEP 3: Call super to continue with normal confirmation
        result = super().button_confirm()

        # STEP 4: CRITICAL - Restore RG5329 taxes AFTER confirmation if they were removed
        for order in self:
            if not self.env.context.get('skip_rg5329_confirm'):
                order._restore_rg5329_taxes_after_confirm()

        return result

    def _store_rg5329_taxes_before_confirm(self):
        """
        Store which lines have RG5329 taxes BEFORE confirmation
        This allows us to restore them if they get removed during confirmation
        """
        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase')
        ], limit=1)

        if not rg5329_tax:
            return

        # Store line IDs that should have RG5329 tax
        lines_with_rg5329 = []
        for line in self.order_line:
            if rg5329_tax.id in line.taxes_id.ids:
                lines_with_rg5329.append(line.id)
                _logger.info("RG5329 STORE: Line %s (product: %s) has RG5329 tax before confirmation",
                           line.id, line.product_id.name if line.product_id else 'No product')

        # Store in context for later retrieval
        self.env.context = dict(self.env.context, rg5329_lines_before_confirm=lines_with_rg5329)
        _logger.info("RG5329 STORE: Stored %d lines with RG5329 tax", len(lines_with_rg5329))

    def _restore_rg5329_taxes_after_confirm(self):
        """
        Restore RG5329 taxes AFTER confirmation if they were removed
        This is the critical fix for the disappearing tax issue
        """
        # Get stored line IDs from context
        lines_with_rg5329 = self.env.context.get('rg5329_lines_before_confirm', [])
        if not lines_with_rg5329:
            _logger.info("RG5329 RESTORE: No lines to restore")
            return

        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase')
        ], limit=1)

        if not rg5329_tax:
            _logger.warning("RG5329 RESTORE: RG5329 tax not found!")
            return

        restored_count = 0
        for line in self.order_line:
            if line.id in lines_with_rg5329:
                # Check if tax is missing
                if rg5329_tax.id not in line.taxes_id.ids:
                    _logger.warning("RG5329 RESTORE: Tax missing from line %s (product: %s) - RESTORING",
                                  line.id, line.product_id.name if line.product_id else 'No product')

                    # Restore the tax
                    current_tax_ids = list(line.taxes_id.ids)
                    current_tax_ids.append(rg5329_tax.id)
                    line.write({'taxes_id': [(6, 0, current_tax_ids)]})
                    restored_count += 1
                else:
                    _logger.info("RG5329 RESTORE: Tax still present on line %s - OK", line.id)

        if restored_count > 0:
            _logger.info("RG5329 RESTORE: ✅ Restored RG5329 tax to %d lines", restored_count)
            # Force recalculation of totals
            self._amount_all()
        else:
            _logger.info("RG5329 RESTORE: All taxes preserved correctly")

    def _apply_rg5329_logic(self):
        """
        UNIFIED RG5329 Logic for Purchase Orders
        Applies RG5329 tax automatically based on:
        1. Supplier is IVA Responsable Inscripto (code '1')
        2. Product has apply_rg5329 = True
        3. Order total >= $100,000 (TOTAL CON IVA, no subtotal)
        """
        if self.state not in ['draft', 'sent'] or self.env.context.get('applying_rg5329'):
            return True

        # Force recalculation of totals first
        self.with_context(applying_rg5329=True)._amount_all()

        # IMPORTANTE: Calculamos el total SIN el impuesto RG5329 para evitar recursión
        # El mínimo de $100k se refiere al total con IVA pero SIN la percepción RG5329
        rg5329_tax_amount = 0
        for line in self.order_line:
            for tax in line.taxes_id:
                if tax.is_rg5329_perception:
                    # Calcular cuánto es el impuesto RG5329 en esta línea
                    tax_result = tax.compute_all(
                        line.price_unit,
                        self.currency_id,
                        line.product_qty,
                        line.product_id,
                        self.partner_id
                    )
                    rg5329_tax_amount += tax_result['total_included'] - tax_result['total_excluded']

        # Total con IVA pero SIN percepción RG5329
        total = (self.amount_total or 0) - rg5329_tax_amount
        _logger.info("=== RG5329 UNIFIED: Processing purchase order %s with total $%s (with VAT, without RG5329) ===",
                    self.name or 'New', total)

        # Find RG5329 tax for purchases
        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase')
        ], limit=1)

        if not rg5329_tax:
            _logger.warning("RG5329 UNIFIED: No RG5329 purchase tax found!")
            return False

        _logger.info("RG5329 UNIFIED: Found RG5329 tax: %s (ID: %s)", rg5329_tax.name, rg5329_tax.id)

        # Debug order line info
        _logger.info("RG5329 DEBUG: Purchase order has %d lines", len(self.order_line))
        _logger.info("RG5329 DEBUG: Purchase order line IDs: %s", [line.id for line in self.order_line])

        # Process all lines at once
        line_count = 0
        for line in self.order_line:
            line_count += 1
            _logger.info("RG5329 DEBUG: Processing line with product: %s",
                        line.product_id.name if line.product_id else 'No product')

            # Only process products marked for RG5329
            if not (line.product_id and line.product_id.apply_rg5329):
                _logger.info("RG5329 DEBUG: Skipping line - product not marked for RG5329")
                continue

            _logger.info("RG5329 DEBUG: Line has RG5329 product, checking supplier conditions...")

            # Skip if supplier is exempt
            if self.partner_id and self.partner_id.rg5329_exempt:
                _logger.info("RG5329 DEBUG: Supplier is exempt")
                # Remove tax if supplier is exempt
                if rg5329_tax.id in line.taxes_id.ids:
                    new_taxes = line.taxes_id.filtered(lambda t: t.id != rg5329_tax.id)
                    line.write({'taxes_id': [(6, 0, new_taxes.ids)]})
                    _logger.info("RG5329 UNIFIED: Removed tax - supplier exempt")
                continue

            _logger.info("RG5329 DEBUG: Supplier not exempt, checking eligibility...")

            # Check if supplier is eligible (only Responsable Inscripto)
            if not self._is_partner_eligible_for_rg5329():
                _logger.info("RG5329 DEBUG: Supplier not eligible for RG5329")
                # Remove tax if supplier not eligible
                if rg5329_tax.id in line.taxes_id.ids:
                    new_taxes = line.taxes_id.filtered(lambda t: t.id != rg5329_tax.id)
                    line.write({'taxes_id': [(6, 0, new_taxes.ids)]})
                    _logger.info("RG5329 UNIFIED: Removed tax - supplier not eligible")
                continue

            _logger.info("RG5329 DEBUG: Supplier eligible! Proceeding with tax logic...")

            has_tax = rg5329_tax.id in line.taxes_id.ids

            if total >= 100000:
                # ADD tax if not present
                if not has_tax:
                    current_tax_ids = list(line.taxes_id.ids)  # Convert to list to avoid issues
                    if rg5329_tax.id not in current_tax_ids:  # Double check
                        current_tax_ids.append(rg5329_tax.id)
                        line.with_context(skip_onchange=True).write({'taxes_id': [(6, 0, current_tax_ids)]})
                        _logger.info("RG5329 UNIFIED: ✅ ADDED tax - total $%s >= $100k", total)

                        # Force UI refresh
                        self._force_ui_refresh()
                else:
                    _logger.info("RG5329 UNIFIED: ✅ Tax already present - total $%s >= $100k", total)
            else:
                # REMOVE tax if present
                if has_tax:
                    current_tax_ids = [t_id for t_id in line.taxes_id.ids if t_id != rg5329_tax.id]
                    line.with_context(skip_onchange=True).write({'taxes_id': [(6, 0, current_tax_ids)]})
                    _logger.info("RG5329 UNIFIED: ❌ REMOVED tax - total $%s < $100k", total)

                    # Force UI refresh
                    self._force_ui_refresh()
                else:
                    _logger.info("RG5329 UNIFIED: ❌ Tax already not present - total $%s < $100k", total)

        _logger.info("RG5329 DEBUG: Processed %d lines total", line_count)
        return True

    def _is_partner_eligible_for_rg5329(self):
        """
        Check if supplier is eligible for RG 5329
        Only applies to IVA Responsable Inscripto (code '1')
        """
        try:
            partner = self.partner_id

            if not hasattr(partner, 'l10n_ar_afip_responsibility_type_id'):
                _logger.warning("RG5329 UNIFIED: No AFIP responsibility field found")
                return False

            if not partner.l10n_ar_afip_responsibility_type_id:
                _logger.info("RG5329 UNIFIED: Partner %s - no fiscal responsibility configured", partner.name)
                return False

            responsibility_code = partner.l10n_ar_afip_responsibility_type_id.code
            is_eligible = responsibility_code == '1'  # IVA Responsable Inscripto

            _logger.info("RG5329 UNIFIED: Partner %s - code %s - eligible: %s",
                        partner.name, responsibility_code, is_eligible)

            return is_eligible

        except Exception as e:
            _logger.error("RG5329 UNIFIED: Error checking eligibility: %s", str(e))
            return False

    def _force_ui_refresh(self):
        """Force UI refresh after tax changes"""
        try:
            # Invalidate computed fields cache
            self.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])

            # Force recomputation
            self._amount_all()

            # Notify UI of changes
            if hasattr(self.env['bus.bus'], '_sendone'):
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id,
                    'purchase_order/rg5329_updated',
                    {'order_id': self.id}
                )

            _logger.info("RG5329 UNIFIED: UI refresh triggered")

        except Exception as e:
            _logger.error("RG5329 UNIFIED: Error forcing UI refresh: %s", str(e))

    @api.onchange('partner_id')
    def _onchange_partner_rg5329_unified(self):
        """Trigger RG5329 recalculation when partner changes"""
        if self.partner_id and not self.env.context.get('skip_onchange'):
            _logger.info("RG5329 UNIFIED: Partner changed, triggering logic...")
            self._apply_rg5329_logic()

    def _amount_all(self):
        """Override _amount_all to trigger RG5329 logic after totals are calculated"""
        result = super()._amount_all()

        # Trigger RG5329 logic after amounts are computed (but avoid infinite loops)
        if (not self.env.context.get('applying_rg5329') and
            not self.env.context.get('skip_rg5329_auto')):

            for order in self:
                if order.state in ['draft', 'sent']:
                    # Only trigger if there are RG5329 products
                    has_rg5329_products = any(
                        line.product_id and line.product_id.apply_rg5329
                        for line in order.order_line
                    )
                    if has_rg5329_products:
                        _logger.info("RG5329 UNIFIED: Amounts computed, checking RG5329 logic...")
                        order.with_context(skip_rg5329_auto=True)._apply_rg5329_logic()

        return result

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _get_stock_move_price_unit(self):
        """
        Override to ensure RG5329 taxes are properly included in stock move price calculation.
        This prevents the tax from disappearing during confirmation.
        """
        # Find RG5329 tax
        rg5329_tax = self.env['account.tax'].sudo().search([
            ('is_rg5329_perception', '=', True),
            ('amount', '=', 3.0),
            ('type_tax_use', '=', 'purchase')
        ], limit=1)

        # Check if this line SHOULD have RG5329 tax
        # IMPORTANTE: Calcular total sin el impuesto RG5329 para evitar recursión
        if self.order_id:
            rg5329_tax_amount = 0
            for line in self.order_id.order_line:
                for tax in line.taxes_id:
                    if tax.is_rg5329_perception:
                        tax_result = tax.compute_all(
                            line.price_unit, self.order_id.currency_id,
                            line.product_qty, line.product_id, self.order_id.partner_id
                        )
                        rg5329_tax_amount += tax_result['total_included'] - tax_result['total_excluded']
            order_total_without_rg5329 = (self.order_id.amount_total or 0) - rg5329_tax_amount
        else:
            order_total_without_rg5329 = 0

        should_have_rg5329 = (
            rg5329_tax and
            self.product_id and
            self.product_id.apply_rg5329 and
            self.order_id and
            order_total_without_rg5329 >= 100000 and
            not (self.order_id.partner_id and self.order_id.partner_id.rg5329_exempt)
        )

        if should_have_rg5329 and rg5329_tax.id not in self.taxes_id.ids:
            _logger.warning("RG5329: Line missing RG5329 tax during stock move creation - ADDING IT")
            # Add the tax before calculating price
            current_tax_ids = list(self.taxes_id.ids)
            current_tax_ids.append(rg5329_tax.id)
            self.write({'taxes_id': [(6, 0, current_tax_ids)]})

        _logger.info("RG5329: Getting stock move price unit for line with product %s, taxes: %s",
                     self.product_id.name if self.product_id else 'No product',
                     [t.name for t in self.taxes_id])

        # Call super with taxes properly set
        result = super()._get_stock_move_price_unit()

        _logger.info("RG5329: Stock move price unit calculated: %s (taxes used: %s)",
                     result, [t.name for t in self.taxes_id])
        return result

    @api.onchange('product_qty', 'price_unit', 'product_id')
    def _onchange_rg5329_unified(self):
        """Trigger RG5329 recalculation when line values change"""
        if (self.order_id and
            not self.env.context.get('applying_rg5329') and
            not self.env.context.get('skip_onchange')):
            _logger.info("RG5329 UNIFIED: Line changed, triggering logic...")
            self.order_id._apply_rg5329_logic()

    def write(self, vals):
        """Override write to trigger RG5329 recalculation when line changes"""
        result = super().write(vals)

        # Only trigger for critical changes and avoid loops
        critical_fields = ['product_qty', 'price_unit', 'product_id']
        if (not self.env.context.get('applying_rg5329') and
            not self.env.context.get('skip_onchange') and
            any(field in vals for field in critical_fields) and
            'taxes_id' not in vals):  # Don't trigger if we're updating taxes

            orders_to_recalc = set()
            for line in self:
                if line.order_id and line.order_id.state in ['draft', 'sent']:
                    orders_to_recalc.add(line.order_id.id)

            # Trigger for all affected orders with context to prevent loops
            for order_id in orders_to_recalc:
                order = self.env['purchase.order'].browse(order_id)
                _logger.info("RG5329 UNIFIED: Line write triggered for purchase order %s", order.name)
                order.with_context(skip_onchange=True)._apply_rg5329_logic()

        return result
