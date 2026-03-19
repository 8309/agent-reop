import pytest
from mathlib import add, subtract, multiply, divide


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 4) == 6


def test_multiply():
    assert multiply(3, 7) == 21


def test_divide():
    assert divide(10, 2) == 5.0


def test_divide_by_zero():
    """This test currently FAILS because divide() has no zero-guard."""
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(1, 0)
