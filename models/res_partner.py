from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    rg5329_exempt = fields.Boolean(
        string='Exento RG 5329',
        help='Indica si el cliente está exento del régimen de percepción RG 5329',
        default=False
    )

    def _is_rg5329_eligible(self):
        """
        Determina si el partner es sujeto de percepción RG 5329.
        Solo aplica a IVA Responsable Inscripto (código AFIP '1').
        Retorna False también si el partner tiene rg5329_exempt=True.
        """
        try:
            if self.rg5329_exempt:
                return False

            if not hasattr(self, 'l10n_ar_afip_responsibility_type_id'):
                _logger.warning("RG5329: No AFIP responsibility field found on partner %s", self.name)
                return False

            if not self.l10n_ar_afip_responsibility_type_id:
                _logger.debug("RG5329: Partner %s has no fiscal responsibility configured", self.name)
                return False

            is_eligible = self.l10n_ar_afip_responsibility_type_id.code == '1'
            _logger.debug("RG5329: Partner %s (code %s) eligible: %s",
                          self.name, self.l10n_ar_afip_responsibility_type_id.code, is_eligible)
            return is_eligible

        except Exception as e:
            _logger.error("RG5329: Error checking eligibility for partner %s: %s", self.name, str(e))
            return False
