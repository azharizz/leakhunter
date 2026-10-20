"""The synthetic application verified and published by Unspool CI."""


def profile(record):
    return {"customer_id": record["customer_id"], "display_name": record["display_name"]}
