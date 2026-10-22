"""Synthetic accounts service (gate-experiment safe baseline)."""

PUBLIC_FIELDS = ("user_id", "display_name", "plan")


def _public(user):
    return {field: user[field] for field in PUBLIC_FIELDS}


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
                return {"error": "incomplete_record"}
    return {"error": "not_found", "user_id": user_id}
