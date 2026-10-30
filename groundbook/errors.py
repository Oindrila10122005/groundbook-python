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


class Overlap(DomainError):
    """The shadow clashes with another live booking's shadow; `clashes_with` lists them with their held ranges."""
    status, type, title = 409, "/errors/overlap", "The interval, with its buffers, overlaps another booking"


class AlreadyStarted(DomainError):
    status, type, title = 409, "/errors/already-started", "The interval has begun; it can no longer be confirmed or moved"


class AlreadyOver(DomainError):
    status, type, title = 409, "/errors/already-over", "The interval has ended; it can no longer be cancelled"


class Cancelled(DomainError):
    status, type, title = 409, "/errors/cancelled", "A cancelled booking cannot be confirmed or moved; request a new one"


class AlreadyConfirmed(DomainError):
    status, type, title = 409, "/errors/already-confirmed", "The booking is already confirmed"


class AlreadyCancelled(DomainError):
    status, type, title = 409, "/errors/already-cancelled", "The booking is already cancelled"


#  and (status, type, title) of the refusals the framework raises before a route runs.
VALIDATION = (422, "/errors/validation", "The request body is not valid")
FILTER = (400, "/errors/validation", "Invalid query parameter")