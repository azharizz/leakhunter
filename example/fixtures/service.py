"""Customer support service with paired unsafe and policy-compliant flows."""
import logging

import analytics
import repository

logger = logging.getLogger("customer-service")
logger.setLevel(logging.INFO)


def customer_response(customer_id="cust-alice", tenant="tenant-a"):
    customer = repository.authorized_customer(customer_id, tenant)
    # Deliberate defect: a database record is not a response schema.
    return {"customer_id": customer.customer_id, "display_name": customer.display_name,
            "email": customer.email, "password_hash": customer.password_hash,
            "session_token": customer.session_token}


def customer_profile(customer_id="cust-alice", tenant="tenant-a"):
    customer = repository.authorized_customer(customer_id, tenant)
    return {"customer_id": customer.customer_id, "display_name": customer.display_name,
            "email": customer.email}


def audit_customer(customer_id="cust-alice", tenant="tenant-a"):
    customer = repository.authorized_customer(customer_id, tenant)
    logger.info("customer=%s email=%s", customer.customer_id, customer.email)
    return {"recorded": True, "customer_id": customer.customer_id}


def audit_safe(customer_id="cust-alice", tenant="tenant-a"):
    customer = repository.authorized_customer(customer_id, tenant)
    logger.info("customer=%s action=profile_view", customer.customer_id)
    return {"recorded": True, "customer_id": customer.customer_id}


def track_customer(customer_id="cust-alice", tenant="tenant-a"):
    customer = repository.authorized_customer(customer_id, tenant)
    analytics.track("profile_view", {"email": customer.email,
                                    "session_token": customer.session_token})
    return {"accepted": True, "event": "profile_view"}


def track_safe():
    analytics.track("catalog_view", {"page": "pricing"})
    return {"accepted": True, "event": "catalog_view"}


def tenant_export_unsafe(customer_id="cust-bob", tenant="tenant-a"):
    # Deliberate defect: tenant is accepted at the boundary but never checked.
    customer = repository.get_customer(customer_id)
    return {"customer_id": customer.customer_id, "address": customer.address}


def tenant_export(customer_id="cust-bob", tenant="tenant-a"):
    try:
        customer = repository.authorized_customer(customer_id, tenant)
    except PermissionError:
        return {"error": "forbidden"}
    return {"customer_id": customer.customer_id, "address": customer.address}


def public_catalog():
    return {"service": "Synthetic Customer Desk", "products": repository.catalog()}
