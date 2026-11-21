from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    bosta_state = fields.Char("Bosta Status", readonly=True, copy=False, tracking=True)
