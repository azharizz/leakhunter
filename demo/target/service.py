"""The synthetic application verified and published by Unspool CI."""

PUBLIC_FIELDS = ("customer_id", "display_name")
MAX_DISPLAY_NAME_LENGTH = 64
ZERO_WIDTH_SPACE = "\u200b"
ZERO_WIDTH_NON_JOINER = "\u200c"
ZERO_WIDTH_JOINER = "\u200d"
ZERO_WIDTH_NO_BREAK_SPACE = "\ufeff"
WORD_SEPARATORS = (
    ZERO_WIDTH_SPACE,
    ZERO_WIDTH_NON_JOINER,
    ZERO_WIDTH_JOINER,
    ZERO_WIDTH_NO_BREAK_SPACE,
)


def profile(record):
    display_name = record["display_name"]
    for separator in WORD_SEPARATORS:
        display_name = display_name.replace(separator, " ")
    display_name = " ".join(display_name.split())
    # Imported rows must never choose the response columns; only public fields leave.
    public = {field: record[field] for field in PUBLIC_FIELDS}
    public["display_name"] = display_name[:MAX_DISPLAY_NAME_LENGTH].rstrip() or record["customer_id"]
    return public
