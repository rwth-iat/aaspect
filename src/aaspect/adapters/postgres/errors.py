"""Which database errors the uploaded content causes, and how errors are logged."""

import traceback

import psycopg

# Refusals seen for values that pass straight from the uploaded files into the database.
# Other errors point at the server or a broken query, which must fail the step instead of
# every document.
# \u0000 inside JSON, or a character the database's encoding lacks.
_UNTRANSLATABLE = "22P05"
_INVALID_TEXT = "22P02"
_LIMIT_EXCEEDED = "54000"  # e.g. an index entry above the size limit


def content_fault(error: BaseException) -> str | None:
    """Why the content the statement worked on is at fault, or None if the server or the
    query is."""
    if isinstance(error, UnicodeEncodeError):
        return "content cannot be stored: it contains text that is not valid Unicode"
    if not isinstance(error, psycopg.Error):
        return None
    state = error.sqlstate
    if state is None and isinstance(error, psycopg.DataError):
        # Without a state, psycopg refused a NUL in a text value before sending it.
        return "content cannot be stored: it contains a NUL character"
    if state == _UNTRANSLATABLE:
        return "content cannot be stored: it contains a character the database cannot hold"
    if state == _LIMIT_EXCEEDED:
        return "content cannot be stored: a value is larger than the database allows"
    return None


def upload_fault(error: BaseException) -> str | None:
    """`content_fault` for a statement that stores uploaded content. Invalid text there
    can only come from the files: the upload casts nothing else, and JSON with NaN or
    Infinity is the case seen. Elsewhere it would mean a cast in a query went wrong."""
    reason = content_fault(error)
    if reason is None and getattr(error, "sqlstate", None) == _INVALID_TEXT:
        return "content cannot be stored: it contains a value JSON does not allow, such as NaN"
    return reason


def described(error: BaseException) -> str:
    """Type, SQLSTATE and stack of `error`, without its message: messages can quote values
    from the uploaded files, which do not belong in the server log."""
    state = getattr(error, "sqlstate", None)
    code = f" {state}" if state else ""
    stack = "".join(traceback.format_tb(error.__traceback__))
    return f"{type(error).__name__}{code}\n{stack}"
