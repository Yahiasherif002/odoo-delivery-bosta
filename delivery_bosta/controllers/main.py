import hmac
import json

from odoo import http
from odoo.http import request

from ..models.delivery_carrier import BOSTA_STATES


class BostaWebhook(http.Controller):

    @http.route("/delivery_bosta/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def bosta_webhook(self):
        try:
            body = json.loads(request.httprequest.get_data())
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return request.make_json_response({"error": "expected a JSON object"}, status=400)

        tracking_number = str(body.get("trackingNumber") or "")
        picking = tracking_number and request.env["stock.picking"].sudo().search(
            [("carrier_tracking_ref", "=", tracking_number), ("carrier_id.delivery_type", "=", "bosta")],
            limit=1,
        )
        if not picking:
            return request.make_json_response({"status": "ignored"})

        secret = (picking.carrier_id.bosta_webhook_secret or "").encode()
        received = request.httprequest.headers.get("Authorization", "").encode()
        if not secret or not hmac.compare_digest(secret, received):
            return request.make_json_response({"error": "unauthorized"}, status=401)

        state = body.get("state")
        try:
            label = BOSTA_STATES.get(int(state))
        except (TypeError, ValueError):
            label = None
        picking.bosta_state = label or f"State {state}"
        return request.make_json_response({"status": "ok"})
