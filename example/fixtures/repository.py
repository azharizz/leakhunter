"""Storage boundary, intentionally small enough to inspect end to end."""
from models import CUSTOMERS, Customer


def get_customer(customer_id: str) -> Customer:
    try:
        return CUSTOMERS[customer_id]
    except KeyError:
        raise LookupError("Customer not found") from None


def authorized_customer(customer_id: str, tenant: str) -> Customer:
    customer = get_customer(customer_id)
    if customer.tenant_id != tenant:
        raise PermissionError("Customer belongs to another tenant")
    return customer


def catalog() -> list[dict]:
    return [{"sku": "plan-team", "name": "Team", "price_cents": 2900},
            {"sku": "plan-business", "name": "Business", "price_cents": 9900}]
