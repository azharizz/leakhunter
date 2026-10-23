"""Built-in sensitive-field catalogue: used when no policy is given, or added with ``extends: builtin``.

Selectors are field-name patterns, so a field nobody listed is still classified when its name looks
sensitive. They are a starting point, not a substitute for an approved operator policy.
"""

SECRET_FIELDS = ("password*", "passwd", "*secret*", "*token*", "*api_key*", "*apikey*", "*private_key*",
                 "card_number", "cvv", "cvc", "ssn", "iban")
PII_FIELDS = ("email", "phone*", "date_of_birth", "address")
SINKS = ("HTTP_RESPONSE", "APPLICATION_LOG", "WEBHOOK", "THIRD_PARTY_ANALYTICS", "AI_PROMPT")

BUILTIN = {
    "version": 1,
    "status": "approved",
    "approved_by": "Unspool built-in catalogue",
    "classifications": {"PUBLIC": 0, "PII": 1, "SECRET": 2},
    "sources": [{"selector": f"*.{name}", "class": "SECRET"} for name in SECRET_FIELDS]
               + [{"selector": f"*.{name}", "class": "PII"} for name in PII_FIELDS],
    "sinks": [{"kind": kind, "allow": ["PUBLIC"]} for kind in SINKS],
    "invariants": ["secret_fields_never_in_external_payloads", "no_real_secrets_in_test_artifacts"],
}
