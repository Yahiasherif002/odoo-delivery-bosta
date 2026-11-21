# Bosta Shipping for Odoo 19

[![CI](https://github.com/Yahiasherif002/odoo-delivery-bosta/actions/workflows/ci.yml/badge.svg)](https://github.com/Yahiasherif002/odoo-delivery-bosta/actions/workflows/ci.yml)

An Odoo 19 module that adds [Bosta](https://bosta.co), an Egyptian courier, as a shipping provider. Delivery orders
are sent to Bosta when they are validated, the tracking number lands on the transfer, and Bosta's status updates flow
back into Odoo.

## What it does

- **Bosta as a delivery method.** Choose "Bosta" as the provider on a delivery method, then use it on sales orders
  like any other carrier.
- **Creates the Bosta delivery.** Validating a delivery order (or clicking "Send to Shipper") creates the delivery
  through Bosta's API v2 and stores the tracking number on the transfer. Customers get a link to Bosta's public
  tracking page.
- **Cash on delivery.** When the sales order was paid with Odoo's own Cash on Delivery payment method, the order total
  is sent to Bosta as the amount to collect. Prepaid orders are sent without it.
- **Live status updates.** Each delivery is created with this database's webhook URL and a secret Authorization value.
  Bosta posts every state change (picked up, delivered, returned, and so on) to `/delivery_bosta/webhook`, and the
  status is recorded on the transfer and in its chatter. Repeated updates add no duplicate chatter entries.
- **Safe by default.** Status updates without the right Authorization value get a 401. The API key and the webhook
  value are visible to administrators only. Addresses are checked before anything is sent (a street of more than
  five characters, a governorate or city, a phone number), and Bosta's own error message is shown when it rejects a
  delivery.

## Setup

1. Install the module (it depends on `stock_delivery`).
2. In Bosta, create an API key under Settings > API Integration. Odoo only needs a key that can create deliveries.
3. In Odoo, go to Inventory > Configuration > Delivery Methods, create a method, and set the provider to **Bosta**.
4. On the **Bosta** tab, paste the API key, choose a webhook Authorization value (any long random string), and set
   the price shown to customers. Restrict the method to Egypt on the **Availability** tab.
5. Make sure the base URL (`web.base.url`) is the public address of your Odoo, so Bosta can reach the webhook.

## How addresses are mapped

| Bosta field | Odoo source |
| --- | --- |
| `dropOffAddress.city` | The partner's state (governorate), or the city if no state is set |
| `dropOffAddress.firstLine` | Street |
| `dropOffAddress.secondLine` | Street 2 |
| `receiver` | Partner name (split into first and last name), phone, email |
| `businessReference` | The sales order number, or the transfer name |
| `specs.packageDetails` | Total quantity and product names on the transfer |
| `cod` | Order total, only for Cash on Delivery orders |

The city must be a name Bosta recognises, such as Cairo, Giza, or Alexandria. If it is not, Bosta answers "City Not
Found" and the module shows that message on the transfer.

## Limitations

- **Rates** use the delivery method's fixed price, because Bosta prices depend on each business's contract.
- **Cancelling** from Odoo is not supported yet: Bosta's public docs do not show the path of its terminate endpoint, so
  the module does not guess it. Cancel in the Bosta dashboard; the cancellation then arrives through the webhook.
- **District and zone IDs** are not sent yet. Bosta resolves the address from the city and street lines.
- **Only standard deliveries** (Bosta type 10) are created. Exchanges, returns, and cash collection are not covered.
- **Tested against mocked Bosta responses** built from Bosta's documentation. It has not yet been run against a live
  Bosta account.

## Tests

The tests cover the request sent to Bosta, cash on delivery, the tracking link, address validation, Bosta errors,
and the webhook (valid updates, retries, unknown states, wrong secrets, unknown deliveries, malformed bodies). They
run on Odoo 19 and PostgreSQL 16 in Docker:

```bash
docker compose up -d db
docker compose run --rm odoo odoo -d test -i delivery_bosta --test-tags /delivery_bosta --stop-after-init
```

CI runs the same command on every push.

## Repository layout

| Path | Contents |
| --- | --- |
| `delivery_bosta/models/delivery_carrier.py` | The Bosta provider: rate, send, tracking link, cancel, and the request payload |
| `delivery_bosta/models/stock_picking.py` | The Bosta status field on transfers |
| `delivery_bosta/controllers/main.py` | The webhook that receives Bosta's status updates |
| `delivery_bosta/views/` | The Bosta tab on delivery methods and the status on transfers |
| `delivery_bosta/tests/` | Unit and HTTP tests |

## License

LGPL-3.0, the same license as Odoo Community.
