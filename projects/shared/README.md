# Shared Contracts

This folder holds the contracts and helpers that every `RepoOps` execution path should agree on.

## Why this exists

If you compare multiple `RepoOps` execution paths, the comparison is only fair when they share:

- the same input fixture
- the same output contract
- the same acceptance criteria

That is why the parsing and payload-building logic lives here instead of being duplicated.
