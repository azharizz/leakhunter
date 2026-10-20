"""The synthetic application verified and published by Unspool CI."""

PUBLIC_FIELDS = ("customer_id", "display_name")
ZERO_WIDTH_SPACE = "\u200b"


def profile(record):
    public = {field: record[field] for field in PUBLIC_FIELDS}
    display_name = public["display_name"].replace(ZERO_WIDTH_SPACE, " ")
    public["display_name"] = " ".join(display_name.split())
    return public
