"""Run with python server.py --serve, or python server.py --route /catalog."""
import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import service

ROUTES = {
    "/catalog": service.public_catalog,
    "/customers/profile": service.customer_profile,
    "/customers/unsafe-response": service.customer_response,
    "/audit": service.audit_safe,
    "/audit/unsafe": service.audit_customer,
    "/analytics": service.track_safe,
    "/analytics/unsafe": service.track_customer,
    "/tenant/export": service.tenant_export,
    "/tenant/unsafe-export": service.tenant_export_unsafe,
}


def dispatch(path, customer_id="cust-alice", tenant="tenant-a"):
    handler = ROUTES.get(path)
    if handler is None:
        return 404, {"error": "not_found"}
    try:
        result = handler() if path in {"/catalog", "/analytics"} else handler(customer_id, tenant)
    except PermissionError:
        return 403, {"error": "forbidden"}
    except LookupError:
        return 404, {"error": "not_found"}
    return (403 if result.get("error") == "forbidden" else 200), result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        status, payload = dispatch(parsed.path, query.get("customer_id", ["cust-alice"])[0],
                                   self.headers.get("X-Tenant", "tenant-a"))
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Synthetic customer service; never expose publicly")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--route", default="/catalog", choices=sorted(ROUTES))
    parser.add_argument("--customer-id", default="cust-alice")
    parser.add_argument("--tenant", default="tenant-a")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.serve:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
        print(f"Synthetic service: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    else:
        status, payload = dispatch(args.route, args.customer_id, args.tenant)
        print(json.dumps({"status": status, "body": payload}, indent=2))


if __name__ == "__main__":
    main()
