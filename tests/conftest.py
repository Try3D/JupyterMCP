"""Shared test fixtures."""

import os
import tempfile

import pytest


@pytest.fixture
def tmp_notebook_dir():
    """Create a temporary directory for test notebooks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def notebook_path(tmp_notebook_dir):
    """Return a path for a test notebook."""
    return os.path.join(tmp_notebook_dir, "test.ipynb")
