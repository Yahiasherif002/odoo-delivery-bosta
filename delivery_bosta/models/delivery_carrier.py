import json

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

BOSTA_API_URL = "https://app.bosta.co/api/v2"
BOSTA_TRACKING_URL = "https://bosta.co/en-eg/tracking-shipments?shipment-number=%s"
BOSTA_TIMEOUT = 30
BOSTA_TYPE_DELIVER = 10
BOSTA_STATES = {
    10: "Pickup requested",
    20: "Route assigned",
    21: "Picked up from business",
    24: "Received at warehouse",
    30: "In transit between hubs",
    41: "Picked up",
    45: "Delivered",
    46: "Returned to business",
    47: "Exception",
    48: "Terminated",
    49: "Canceled",
    100: "Lost",
    101: "Damaged",
    103: "Awaiting your action",
    105: "On hold",
}


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("bosta", "Bosta")],
        ondelete={"bosta": lambda carriers: carriers.write({"delivery_type": "fixed", "fixed_price": 0})},
    )
    bosta_api_key = fields.Char("Bosta API Key", groups="base.group_system")
    bosta_webhook_secret = fields.Char(
        "Webhook Authorization Value",
        groups="base.group_system",
        help="Bosta sends this value in the Authorization header of every status update. "
        "Status updates without it are rejected.",
    )

    def bosta_rate_shipment(self, order):
        return self.fixed_rate_shipment(order)

    def bosta_send_shipping(self, pickings):
        return [
            {"exact_price": self.fixed_price, "tracking_number": self._bosta_create_delivery(picking)}
            for picking in pickings
        ]

    def bosta_get_tracking_link(self, picking):
        refs = picking.carrier_tracking_ref.split(",")
        if len(refs) == 1:
            return BOSTA_TRACKING_URL % refs[0]
        return json.dumps([[ref, BOSTA_TRACKING_URL % ref] for ref in refs])

    def bosta_cancel_shipment(self, pickings):
        raise UserError(_(
            "Cancel this delivery from your Bosta dashboard. "
            "Odoo updates the Bosta status on the transfer when Bosta reports the cancellation."
        ))

    def _bosta_create_delivery(self, picking):
        api_key = self.sudo().bosta_api_key
        if not api_key:
            raise UserError(_("Set the Bosta API key on the delivery method %s.", self.name))
        payload = self._bosta_delivery_payload(picking)
        api_url = self.env["ir.config_parameter"].sudo().get_param("delivery_bosta.api_url", BOSTA_API_URL)
        self.log_xml(str({k: v for k, v in payload.items() if k != "webhookCustomHeaders"}), "bosta_request")
        try:
            response = requests.post(
                f"{api_url}/deliveries?apiVersion=1",
                json=payload,
                headers={"Authorization": api_key},
                timeout=BOSTA_TIMEOUT,
            )
        except requests.Timeout as error:
            raise UserError(_(
                "Bosta did not answer within %(seconds)s seconds, so it may still have created the delivery. "
                "Search the Bosta dashboard for reference %(reference)s before sending it again.",
                seconds=BOSTA_TIMEOUT,
                reference=payload["businessReference"],
            )) from error
        except requests.RequestException as error:
            raise UserError(_("Could not reach Bosta: %s", error)) from error
        self.log_xml(response.text, "bosta_response")
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not response.ok or data.get("success") is False:
            raise UserError(_(
                "Bosta rejected delivery %(picking)s (HTTP %(status)s): %(message)s",
                picking=picking.name,
                status=response.status_code,
                message=data.get("message") or response.text[:500],
            ))
        tracking_number = (data.get("data") or data).get("trackingNumber")
        if not tracking_number:
            raise UserError(_("Bosta did not return a tracking number for %s.", picking.name))
        picking.bosta_cod_amount = payload.get("cod", 0.0)
        return str(tracking_number)

    def _bosta_delivery_payload(self, picking):
        partner = picking.partner_id
        street = (partner.street or "").strip()
        missing = [
            label
            for label, ok in (
                (_("street (more than 5 characters)"), len(street) > 5),
                (_("state or city"), partner.state_id or partner.city),
                (_("phone"), partner.phone),
            )
            if not ok
        ]
        if missing:
            raise UserError(_(
                "Bosta needs these details on %(partner)s: %(fields)s",
                partner=partner.display_name,
                fields=", ".join(missing),
            ))
        first_name, _sep, last_name = (partner.name or "").strip().partition(" ")
        order = picking.sale_id
        receiver = {"firstName": first_name, "lastName": last_name, "phone": partner.phone}
        if partner.email:
            receiver["email"] = partner.email
        payload = {
            "type": BOSTA_TYPE_DELIVER,
            "specs": {
                "packageDetails": {
                    "itemsCount": int(sum(picking.move_ids.mapped("quantity"))) or 1,
                    "description": ", ".join(picking.move_ids.product_id.mapped("name"))[:250],
                },
            },
            "dropOffAddress": {
                "city": partner.state_id.name or partner.city,
                "firstLine": street,
                "secondLine": partner.street2 or "",
            },
            "receiver": receiver,
            "businessReference": f"{order.name} {picking.name}" if order else picking.name,
            "webhookUrl": f"{self.get_base_url()}/delivery_bosta/webhook",
        }
        secret = self.sudo().bosta_webhook_secret
        if secret:
            payload["webhookCustomHeaders"] = {"Authorization": secret}
        if order.transaction_ids.filtered(lambda tx: tx.provider_id.custom_mode == "cash_on_delivery"):
            already_collected = sum((order.picking_ids - picking).mapped("bosta_cod_amount"))
            remaining = order.currency_id.round(order.amount_total - already_collected)
            if remaining > 0:
                payload["cod"] = remaining
        return payload
