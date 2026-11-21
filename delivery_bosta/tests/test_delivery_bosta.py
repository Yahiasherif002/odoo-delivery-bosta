import json
from unittest.mock import Mock, patch

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

POST = "odoo.addons.delivery_bosta.models.delivery_carrier.requests.post"


def bosta_response(status, body):
    return Mock(ok=status < 400, status_code=status, text=json.dumps(body), json=Mock(return_value=body))


class BostaSetup:

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.carrier = cls.env["delivery.carrier"].create({
            "name": "Bosta",
            "delivery_type": "bosta",
            "product_id": cls.env["product.product"].create(
                {"name": "Bosta Delivery", "type": "service", "list_price": 60.0}
            ).id,
            "bosta_api_key": "test-api-key",
            "bosta_webhook_secret": "hook-secret",
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Mona Adel Hassan",
            "street": "12 Tahrir Street",
            "street2": "Apartment 4",
            "city": "Downtown",
            "state_id": cls.env.ref("base.state_eg_c").id,
            "country_id": cls.env.ref("base.eg").id,
            "phone": "+201000000000",
            "email": "mona@example.com",
        })
        cls.lamp = cls.env["product.product"].create({"name": "Desk Lamp", "type": "consu", "list_price": 450.0})


@tagged("post_install", "-at_install")
class TestBostaShipping(BostaSetup, TransactionCase):

    def setUp(self):
        super().setUp()
        self.order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": self.lamp.id, "product_uom_qty": 2})],
        })
        self.order.set_delivery_line(self.carrier, 60.0)
        self.order.action_confirm()
        self.picking = self.order.picking_ids

    def send(self, body=None, status=200):
        body = body or {"success": True, "data": {"_id": "6650f0", "trackingNumber": 48089608}}
        with patch(POST, return_value=bosta_response(status, body)) as post:
            result = self.carrier.send_shipping(self.picking)
        return result, post

    def test_creates_bosta_delivery_and_returns_tracking_number(self):
        result, post = self.send()

        self.assertEqual(result, [{"exact_price": 60.0, "tracking_number": "48089608"}])
        self.assertEqual(post.call_args.args[0], "https://app.bosta.co/api/v2/deliveries?apiVersion=1")
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "test-api-key"})
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["type"], 10)
        self.assertEqual(payload["specs"]["packageDetails"], {"itemsCount": 2, "description": "Desk Lamp"})
        self.assertEqual(payload["dropOffAddress"], {
            "city": "Cairo", "firstLine": "12 Tahrir Street", "secondLine": "Apartment 4",
        })
        self.assertEqual(payload["receiver"], {
            "firstName": "Mona", "lastName": "Adel Hassan", "phone": "+201000000000", "email": "mona@example.com",
        })
        self.assertEqual(payload["businessReference"], self.order.name)
        self.assertTrue(payload["webhookUrl"].endswith("/delivery_bosta/webhook"))
        self.assertEqual(payload["webhookCustomHeaders"], {"Authorization": "hook-secret"})
        self.assertNotIn("cod", payload)

    def test_collects_order_total_when_paid_cash_on_delivery(self):
        provider = self.env["payment.provider"].create(
            {"name": "Cash on Delivery", "code": "custom", "custom_mode": "cash_on_delivery"}
        )
        self.env["payment.transaction"].create({
            "provider_id": provider.id,
            "payment_method_id": self.env.ref("payment.payment_method_unknown").id,
            "reference": "COD-TEST-1",
            "amount": self.order.amount_total,
            "currency_id": self.order.currency_id.id,
            "partner_id": self.partner.id,
            "sale_order_ids": [(6, 0, self.order.ids)],
        })

        _result, post = self.send()

        self.assertEqual(post.call_args.kwargs["json"]["cod"], self.order.amount_total)

    def test_send_to_shipper_stores_tracking_reference_on_transfer(self):
        with patch(POST, return_value=bosta_response(200, {"success": True, "data": {"trackingNumber": "777"}})):
            self.picking.send_to_shipper()

        self.assertEqual(self.picking.carrier_tracking_ref, "777")
        self.assertEqual(
            self.carrier.get_tracking_link(self.picking),
            "https://bosta.co/en-eg/tracking-shipments?shipment-number=777",
        )

    def test_incomplete_address_is_refused_before_calling_bosta(self):
        self.partner.write({"street": "12", "phone": False})

        with patch(POST) as post, self.assertRaisesRegex(UserError, r"street \(more than 5 characters\), phone"):
            self.carrier.send_shipping(self.picking)
        post.assert_not_called()

    def test_bosta_error_message_is_shown_to_the_user(self):
        with self.assertRaisesRegex(UserError, r"HTTP 400\): City Not Found"):
            self.send({"success": False, "message": "City Not Found"}, status=400)

    def test_missing_api_key_is_refused(self):
        self.carrier.bosta_api_key = False

        with patch(POST) as post, self.assertRaisesRegex(UserError, "Set the Bosta API key"):
            self.carrier.send_shipping(self.picking)
        post.assert_not_called()

    def test_cancel_points_to_the_bosta_dashboard(self):
        with self.assertRaisesRegex(UserError, "Bosta dashboard"):
            self.carrier.cancel_shipment(self.picking)


@tagged("post_install", "-at_install")
class TestBostaWebhook(BostaSetup, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.picking = cls.env["stock.picking"].create({
            "picking_type_id": cls.env.ref("stock.picking_type_out").id,
            "partner_id": cls.partner.id,
            "carrier_id": cls.carrier.id,
            "carrier_tracking_ref": "48089608",
        })

    def post_update(self, body, secret="hook-secret"):
        response = self.url_open(
            "/delivery_bosta/webhook",
            data=json.dumps(body),
            headers={"Content-Type": "application/json", "Authorization": secret},
        )
        self.picking.invalidate_recordset()
        return response

    def test_status_update_is_recorded_on_the_transfer(self):
        response = self.post_update({"trackingNumber": 48089608, "state": 45})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.picking.bosta_state, "Delivered")
        self.assertIn("Delivered", self.picking.message_ids.tracking_value_ids.mapped("new_value_char"))

    def test_repeated_update_adds_no_second_chatter_entry(self):
        self.post_update({"trackingNumber": "48089608", "state": 24})
        messages = len(self.picking.message_ids)

        self.post_update({"trackingNumber": "48089608", "state": 24})

        self.assertEqual(self.picking.bosta_state, "Received at warehouse")
        self.assertEqual(len(self.picking.message_ids), messages)

    def test_unknown_state_code_is_kept_verbatim(self):
        self.post_update({"trackingNumber": "48089608", "state": 999})

        self.assertEqual(self.picking.bosta_state, "State 999")

    def test_wrong_secret_is_rejected(self):
        response = self.post_update({"trackingNumber": "48089608", "state": 45}, secret="guess")

        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.picking.bosta_state)

    def test_update_for_unknown_delivery_is_ignored(self):
        response = self.post_update({"trackingNumber": "123", "state": 45})

        self.assertEqual(response.json(), {"status": "ignored"})

    def test_malformed_body_is_rejected(self):
        response = self.url_open("/delivery_bosta/webhook", data="not json", headers={"Content-Type": "application/json"})

        self.assertEqual(response.status_code, 400)
