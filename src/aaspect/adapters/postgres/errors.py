"""Which database errors the uploaded content causes, and how errors are logged."""

import traceback

import psycopg

# Refusals seen for values that pass straight from the uploaded files into the database.
# Other errors point at the server or a broken query, which must fail the step instead of
# every document.
_UNTRANSLATABLE = "22P05"  # \u0000 inside JSON
_INVALID_TEXT = "22P02"
_LIMIT_EXCEEDED = "54000"  # e.g. an index entry above the size limit
_NOT_JSON = "invalid input syntax for type json"


def content_fault(error: BaseException) -> str | None:
    """Why the content the statement worked on is at fault, or None if the server or the
    query is."""
    if isinstance(error, UnicodeEncodeError):
        return "content cannot be stored: it contains text that is not valid Unicode"
    if not isinstance(error, psycopg.Error):
        return None
    state = error.sqlstate
    if state == _UNTRANSLATABLE or (state is None and isinstance(error, psycopg.DataError)):
        # Without a state, psycopg refused a NUL in a text value before sending it.
        return "content cannot be stored: it contains a NUL character"
    if state == _INVALID_TEXT and (error.diag.message_primary or "").startswith(_NOT_JSON):
        return "content cannot be stored: it contains NaN or Infinity, which JSON does not allow"
    if state == _LIMIT_EXCEEDED:
        return "content cannot be stored: a value is larger than the database allows"
    return None


def described(error: BaseException) -> str:
    """Type, SQLSTATE and stack of `error`, without its message: messages can quote values
    from the uploaded files, which do not belong in the server log."""
    state = getattr(error, "sqlstate", None)
    code = f" {state}" if state else ""
    stack = "".join(traceback.format_tb(error.__traceback__))
    return f"{type(error).__name__}{code}\n{stack}"
