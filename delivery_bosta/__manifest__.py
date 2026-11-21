{
    "name": "Bosta Shipping",
    "version": "19.0.1.0.0",
    "category": "Shipping Connectors",
    "summary": "Send delivery orders to Bosta and follow their status in Odoo",
    "author": "Yahia Sherif",
    "website": "https://github.com/Yahiasherif002/odoo-delivery-bosta",
    "license": "LGPL-3",
    "depends": ["stock_delivery"],
    "data": [
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
}
