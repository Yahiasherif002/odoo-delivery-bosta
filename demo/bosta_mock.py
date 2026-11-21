import itertools
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

tracking_numbers = itertools.count(48089608)


class BostaMock(BaseHTTPRequestHandler):

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path != "/api/v2/deliveries?apiVersion=1" or not self.headers.get("Authorization"):
            self.reply(404, {"success": False, "message": "Not found"})
            return
        print("delivery created:", json.dumps(body), flush=True)
        self.reply(200, {"success": True, "data": {"_id": "demo", "trackingNumber": next(tracking_numbers)}})

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


HTTPServer(("0.0.0.0", 8080), BostaMock).serve_forever()
