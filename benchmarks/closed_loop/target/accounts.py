"""Synthetic accounts service with one deliberately planted exposure (closed-loop case)."""

PUBLIC_FIELDS = ("customer_id", "display_name", "plan")


def account_summary(account):
    public = {field: account[field] for field in PUBLIC_FIELDS}
    public["display_name"] = " ".join(public["display_name"].split())
    return public
