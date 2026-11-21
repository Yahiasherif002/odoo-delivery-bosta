from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    bosta_state = fields.Char("Bosta Status", readonly=True, copy=False, tracking=True)
    bosta_state_timestamp = fields.Float("Bosta Status Time", readonly=True, copy=False)
    bosta_cod_amount = fields.Float("Bosta Cash on Delivery", readonly=True, copy=False)
