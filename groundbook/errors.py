"""Every refusal the app can give, in one shape."""


class DomainError(Exception):
    status: int = 400
    type: str = "/errors/domain"
    title: str = "Refused"

    def __init__(self, detail: str, **extra):
        super().__init__(detail)
        self.detail = detail
        self.extra = extra


class BadInterval(DomainError):
    """A body that passed its Field constraints but asks for something impossible -- `to` not after `from`,
    the past, two dates, or a shadow outside the ground's hours (`opens`/`closes` say the hours)."""
    status, type, title = 400, "/errors/bad-interval", "The interval cannot be booked"


class NoSuchVenue(DomainError):
    status, type, title = 404, "/errors/no-such-venue", "No such venue"


class NoSuchGround(DomainError):
    status, type, title = 404, "/errors/no-such-ground", "No such ground at this venue"


class NoSuchEventType(DomainError):
    status, type, title = 400, "/errors/no-such-event-type", "No such event type at this venue"


class NoSuchBooking(DomainError):
    status, type, title = 404, "/errors/no-such-booking", "No such booking at this venue"


#  and (status, type, title) of the refusals the framework raises before a route runs.
VALIDATION = (422, "/errors/validation", "The request body is not valid")
FILTER = (400, "/errors/validation", "Invalid query parameter")