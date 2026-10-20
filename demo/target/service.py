"""The synthetic application verified and published by Unspool CI."""

PUBLIC_FIELDS = ("customer_id", "display_name")


def profile(record):
    public = {field: record[field] for field in PUBLIC_FIELDS}
    public["display_name"] = " ".join(public["display_name"].split())
    return public
