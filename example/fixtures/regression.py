"""Functional contracts only: a security repair may remove unsafe extra fields."""
import service
from server import dispatch


def main():
    catalog = service.public_catalog()
    assert catalog["products"][0]["sku"] == "plan-team"
    assert catalog["products"][0]["price_cents"] == 2900
    for response in (service.customer_profile(), service.customer_response()):
        assert response["customer_id"] == "cust-alice"
        assert response["display_name"] == "Alice Example"
        assert response["email"] == "alice.synthetic@example.invalid"
    assert service.audit_customer()["recorded"] is True
    assert service.audit_safe()["recorded"] is True
    assert service.track_customer()["accepted"] is True
    assert service.track_safe()["accepted"] is True
    assert service.tenant_export("cust-alice", "tenant-a")["customer_id"] == "cust-alice"
    assert service.tenant_export("cust-bob", "tenant-a") == {"error": "forbidden"}
    assert dispatch("/missing")[0] == 404
    assert dispatch("/customers/profile", "missing")[0] == 404
    assert dispatch("/customers/profile", "cust-bob", "tenant-a")[0] == 403
    assert dispatch("/catalog")[0] == 200
    print("Customer service functional contracts passed")


if __name__ == "__main__":
    main()
