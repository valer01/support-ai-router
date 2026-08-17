"""Sets a fixed, isolated test data dir/DB BEFORE any app.* module is
imported by any test file, avoiding fragile importlib.reload() chains for
modules that cross-reference each other (app.main -> app.seed -> app.db).
pytest imports conftest.py first, so this env is in place for every test's
first `import app...`."""
import os
import tempfile

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="support-ai-router-tests-")
os.environ.setdefault("SUPPORTROUTER_DATA_DIR", _TEST_DATA_DIR)
os.environ.setdefault("SUPPORTROUTER_DATABASE_URL", f"sqlite:///{_TEST_DATA_DIR}/test.db")
os.environ.setdefault("SUPPORTROUTER_SESSION_SECRET", "test-secret")
os.environ.setdefault("SUPPORTROUTER_SEED_USERNAME", "test.admin")
# Note: ANTHROPIC_API_KEY is deliberately left as-is here (not popped) so
# the real-API golden-set accuracy test (test_classification_accuracy.py,
# marked `integration`) can run when the key is present in the
# environment. Unit tests that need it unset patch it explicitly via
# unittest.mock.patch.object(classification_service, "ANTHROPIC_API_KEY", ...).
