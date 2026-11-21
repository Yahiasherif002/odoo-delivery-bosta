import hmac
import json

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..models.delivery_carrier import BOSTA_STATES

MAX_BODY_BYTES = 64 * 1024


class BostaWebhook(http.Controller):

    @http.route("/delivery_bosta/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def bosta_webhook(self):
        received = request.httprequest.headers.get("Authorization", "").encode()
        carriers = request.env["delivery.carrier"].sudo().with_context(active_test=False).search(
            [("delivery_type", "=", "bosta"), ("bosta_webhook_secret", "!=", False)]
        )
        carriers = carriers.filtered(lambda c: hmac.compare_digest(c.bosta_webhook_secret.encode(), received))
        if not carriers:
            return request.make_json_response({"error": "unauthorized"}, status=401)

        if (request.httprequest.content_length or 0) > MAX_BODY_BYTES:
            return request.make_json_response({"error": "body too large"}, status=413)
        raw = request.httprequest.get_data()
        if len(raw) > MAX_BODY_BYTES:
            return request.make_json_response({"error": "body too large"}, status=413)
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return request.make_json_response({"error": "expected a JSON object"}, status=400)

        tracking_number = str(body.get("trackingNumber") or "")
        pickings = tracking_number and request.env["stock.picking"].sudo().search(
            [("carrier_id", "in", carriers.ids), ("carrier_tracking_ref", "ilike", tracking_number)]
        ).filtered(lambda p: tracking_number in p.carrier_tracking_ref.split(","))
        if not pickings:
            return request.make_json_response({"status": "ignored"})

        state = body.get("state")
        try:
            label = BOSTA_STATES.get(int(state))
        except (TypeError, ValueError):
            label = None
        try:
            timestamp = float(body.get("timeStamp"))
        except (TypeError, ValueError):
            timestamp = 0.0
        updated = pickings.with_user(SUPERUSER_ID).filtered(
            lambda p: not timestamp or timestamp >= p.bosta_state_timestamp
        )
        for picking in updated:
            picking.write({
                "bosta_state": label or f"State {str(state)[:20]}",
                "bosta_state_timestamp": timestamp or picking.bosta_state_timestamp,
            })
        return request.make_json_response({"status": "ok" if updated else "outdated"})
