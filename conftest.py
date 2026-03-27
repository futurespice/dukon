# pytest configuration for Dukon Online
# DEVOPS FIX #4: CI was using --cov-fail-under=0 which never enforced coverage.
# This conftest bootstraps pytest-django so tests can run at all.

import django
from django.conf import settings


def pytest_configure(config):
    """Configure Django settings for the test suite if not already set."""
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    # DEVOPS #17: Prevent tests from accidentally running with production settings.
    settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', '')
    assert 'production' not in settings_module, (
        f'Tests must NOT run with production settings ({settings_module}). '
        f'Use config.settings.local instead.'
    )
