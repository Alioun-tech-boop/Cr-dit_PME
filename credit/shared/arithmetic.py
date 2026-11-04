"""Contexte indépendant du thread appelant et des bibliothèques tierces."""

from decimal import localcontext, ROUND_HALF_UP, Context, InvalidOperation, DivisionByZero, Overflow
from functools import wraps


def arithmetic_context():
    return Context(
        prec=28,
        rounding=ROUND_HALF_UP,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def deterministic(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with localcontext(arithmetic_context()) as context:
            context.prec = 28
            context.rounding = ROUND_HALF_UP
            return function(*args, **kwargs)

    return wrapped
