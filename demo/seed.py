import json
import urllib.request

URL, DB, LOGIN, PASSWORD = "http://localhost:8069", "demo", "admin", "admin"


def rpc(service, method, *args):
    request = urllib.request.Request(
        f"{URL}/jsonrpc",
        data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {
            "service": service, "method": method, "args": args,
        }}).encode(),
        headers={"Content-Type": "application/json"},
    )
    reply = json.load(urllib.request.urlopen(request))
    if "error" in reply:
        raise RuntimeError(reply["error"]["data"]["message"])
    return reply.get("result")


uid = rpc("common", "authenticate", DB, LOGIN, PASSWORD, {})


def call(model, method, *args, **kwargs):
    return rpc("object", "execute_kw", DB, uid, PASSWORD, model, method, list(args), kwargs)


def ref(xmlid):
    module, name = xmlid.split(".")
    return call("ir.model.data", "search_read", [("module", "=", module), ("name", "=", name)], fields=["res_id"])[0]["res_id"]


call("ir.config_parameter", "set_param", "delivery_bosta.api_url", "http://bosta-mock:8080/api/v2")
call("res.currency", "write", [ref("base.EGP")], {"active": True})
call("res.company", "write", [1], {"country_id": ref("base.eg"), "currency_id": ref("base.EGP")})
call("product.pricelist", "write", call("product.pricelist", "search", []), {"currency_id": ref("base.EGP")})

carrier = call("delivery.carrier", "create", {
    "name": "Bosta",
    "delivery_type": "bosta",
    "product_id": call("product.product", "create", {
        "name": "Bosta Delivery", "type": "service", "list_price": 60, "taxes_id": [(5, 0, 0)],
    }),
    "bosta_api_key": "demo-api-key",
    "bosta_webhook_secret": "demo-webhook-secret",
    "country_ids": [(6, 0, [ref("base.eg")])],
})
customer = call("res.partner", "create", {
    "name": "Mona Adel Hassan",
    "street": "12 Tahrir Street",
    "street2": "Apartment 4",
    "city": "Downtown",
    "state_id": ref("base.state_eg_c"),
    "country_id": ref("base.eg"),
    "phone": "+20 100 000 0000",
})
lamp = call("product.product", "create", {"name": "Desk Lamp", "type": "consu", "list_price": 450, "taxes_id": [(5, 0, 0)]})

order = call("sale.order", "create", {"partner_id": customer, "order_line": [(0, 0, {"product_id": lamp, "product_uom_qty": 2})]})
wizard = call("choose.delivery.carrier", "create", {"order_id": order, "carrier_id": carrier})
call("choose.delivery.carrier", "update_price", [wizard])
call("choose.delivery.carrier", "button_confirm", [wizard])
call("sale.order", "action_confirm", [order])

picking = call("sale.order", "read", [order], fields=["picking_ids"])[0]["picking_ids"][0]
print(f"carrier={carrier} order={order} picking={picking}")
