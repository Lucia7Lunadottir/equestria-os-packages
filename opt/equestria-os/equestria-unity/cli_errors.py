"""Unity CLI errors in words the user can act on. The CLI reports a code with each error; known codes get a
translated explanation, anything else keeps the CLI's own message."""
from kit import tr

NETWORK = {"ENOTFOUND", "ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "EAI_AGAIN", "ENETUNREACH", "EHOSTUNREACH",
           "NETWORK_ERROR", "PROXY_ERROR"}
NOT_SIGNED_IN = "NOT_SIGNED_IN"
TIMEOUT = "TIMEOUT"


class CliError(str):
    """The CLI's message, carrying its error code (str, so it can go wherever a message went before)."""

    def __new__(cls, message, code=""):
        error = super().__new__(cls, message)
        error.code = code
        return error


def code_of(error):
    return getattr(error, "code", "")


def explain(error, seconds=0):
    """Text for the user: what went wrong and what to do; the CLI's own words for unknown errors.
    The result keeps the error's code, so a caller can still tell "not signed in" from a real failure."""
    code = code_of(error)
    if code in NETWORK:
        text = tr("cli.err.network")
    elif code == "LICENSING_CLIENT_UNAVAILABLE":
        text = tr("cli.err.licensing")
    elif code == NOT_SIGNED_IN:
        text = tr("cli.err.not_signed_in")
    elif code == TIMEOUT:
        text = tr("cli.err.timeout", seconds or "?")
    else:
        return error
    text.code = code
    return text
