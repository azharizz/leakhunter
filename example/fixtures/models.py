"""Synthetic customer records. Never load real customer data into this demo."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Customer:
    customer_id: str
    tenant_id: str
    display_name: str
    email: str
    password_hash: str
    session_token: str
    address: str


CUSTOMERS = {
    "cust-alice": Customer(
        "cust-alice", "tenant-a", "Alice Example", "alice.synthetic@example.invalid",
        "SYNTHETIC_PASSWORD_HASH_ALICE_7e31", "SYNTHETIC_SESSION_ALICE_4f92",
        "SYNTHETIC_ADDRESS_ALICE_81be",
    ),
    "cust-bob": Customer(
        "cust-bob", "tenant-b", "Bob Example", "bob.synthetic@example.invalid",
        "SYNTHETIC_PASSWORD_HASH_BOB_6cd2", "SYNTHETIC_SESSION_BOB_8a01",
        "SYNTHETIC_ADDRESS_BOB_d650",
    ),
}
