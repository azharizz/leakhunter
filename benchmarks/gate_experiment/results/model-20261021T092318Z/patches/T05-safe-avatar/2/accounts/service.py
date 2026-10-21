"""Synthetic accounts service (gate-experiment safe baseline)."""

PUBLIC_FIELDS = ("user_id", "display_name", "plan")
OPTIONAL_PUBLIC_FIELDS = ("avatar_url",)


def _public(user):
    public = {field: user[field] for field in PUBLIC_FIELDS}
    for field in OPTIONAL_PUBLIC_FIELDS:
        public[field] = user.get(field)
    return public


def public_profile(user):
    return _public(user)


def team_listing(users):
    return [_public(user) for user in users]


def lookup(users, user_id):
    for user in users:
        if user["user_id"] == user_id:
            try:
                return _public(user)
            except KeyError:
                return {"error": "incomplete_record", "user_id": user_id}
    return {"error": "not_found", "user_id": user_id}
