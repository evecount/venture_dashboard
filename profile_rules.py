"""
Who counts as "already registered": the double-entry rules for profile setup (pure, no I/O).

Rules
  - One Slack account = one profile (checked by the caller before this).
  - One email = one person, across the whole table.
  - Within the same group (a startup's founders, or the mentor list) a full name is one person unless the
    emails differ: "Alex Lee" + same/no email twice is a duplicate, "Alex Lee" with another email is allowed,
    and "Alex Tan" is a different person.
  - An invited-but-unlinked record (a coordinator pre-registered "Priya Rao", no Slack account yet) is CLAIMED
    by the matching person instead of creating a second record.
  - A typed (unverified) email can never claim an existing record; only Slack's own email can.
"""


def first_name(name: str | None) -> str:
    """What to call someone: the first word, except that a hyphenated given name after it usually means surname-first
    ('Leung Wai-Leng'), so that stays whole. Blank or missing gives 'there'."""
    parts = (name or "").split()
    if not parts:
        return "there"
    return " ".join(parts) if any("-" in p for p in parts[1:]) else parts[0]


def norm_name(name: str) -> str:
    return " ".join((name or "").casefold().split())


def norm_email(email: str) -> str:
    return (email or "").strip().casefold()


def match_person(all_rows: list, scoped_rows: list, name: str, email: str, email_verified: bool):
    """
    Rows are dicts with name, email, slack_user_id. `all_rows` is used for the email check, `scoped_rows` for the name check.
    Returns ("new", None) | ("claim", row) | ("duplicate", row).
    """
    e, n = norm_email(email), norm_name(name)
    if e:
        for r in all_rows:
            if norm_email(r.get("email")) == e:
                if r.get("slack_user_id") or not email_verified:
                    return "duplicate", r
                return "claim", r
    for r in scoped_rows:
        if norm_name(r.get("name")) != n:
            continue
        r_email = norm_email(r.get("email"))
        if r_email and e and r_email != e:
            continue  # same name, different email: a different person
        # only Slack's own email may claim an invited record; a typed one is never proof of who you are
        return ("duplicate", r) if r.get("slack_user_id") or not email_verified else ("claim", r)
    return "new", None


def looks_like_email(value: str) -> bool:
    value = (value or "").strip()
    return "@" in value and "." in value.split("@")[-1] and " " not in value
