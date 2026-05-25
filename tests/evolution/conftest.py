"""Re-export storage fixtures so every test in tests/evolution/ can use
postgresql_proc / postgresql / test_db_url / applied_db without explicitly
importing them. pytest auto-loads this conftest at collection time and
registers the fixture objects by name, so test functions can request them
as parameters and pytest will resolve them via the fixture registry.

Why a conftest instead of the per-file `from tests.storage.conftest import
... # noqa: F401`? Ruff F811 fires when a module-level imported name is
shadowed by a function parameter of the same name (e.g. `def pool(applied_db):`).
The noqa suppresses F401 on the import line but F811 fires at the function
signature, where adding a noqa hurts readability for every fixture-using test.
A conftest re-export sidesteps the shadowing entirely.
"""
from tests.storage.conftest import (  # noqa: F401
    applied_db,
    postgresql,
    postgresql_proc,
    test_db_url,
)
