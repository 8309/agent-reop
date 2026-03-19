"""A tiny math library used as a RepoOps demo target."""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    """Return a / b.

    BUG: does not handle division by zero — raises an unhandled
    ZeroDivisionError instead of returning a clear error.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
