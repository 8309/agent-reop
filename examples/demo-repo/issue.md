# Bug: divide() crashes on division by zero

`mathlib.divide(1, 0)` raises an unhandled `ZeroDivisionError`.

Expected behavior: raise a `ValueError` with the message "Cannot divide by zero".

Acceptance criteria:
- `divide(a, 0)` raises `ValueError("Cannot divide by zero")`
- All existing tests continue to pass
- Add the zero-guard before the division operation
