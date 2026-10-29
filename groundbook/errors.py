"""Domain refusals and their `type` values. No web framework here: services raise these
classes, and `handlers.py` -- the only place that knows about HTTP -- turns each one into application/problem+json.

The class attributes below are the single source of truth for status, type and title.
"""
"""Every refusal the app can give, in one shape."""


class DomainError(Exception):
    status: int = 400
    type: str = "/errors/domain"
    title: str = "Refused"

    def __init__(self, detail: str, **extra):
        super().__init__(detail)
        self.detail = detail
        self.extra = extra


class NoSuchVenue(DomainError):
    status, type, title = 404, "/errors/no-such-venue", "No such venue"


class NoSuchGround(DomainError):
    status, type, title = 404, "/errors/no-such-ground", "No such ground at this venue"


#  and (status, type, title) of the refusals the framework raises before a route runs.
FILTER = (400, "/errors/validation", "Invalid query parameter")
