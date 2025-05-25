"""Pytest configuration and shared fixtures for the test suite."""
import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Generator

from src.domain.path_models import ProjectPathAliases, PathResolutionContext


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    """Create a temporary project directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Create basic project structure
        (temp_dir / "data").mkdir()
        (temp_dir / "config").mkdir()
        (temp_dir / "output").mkdir()
        (temp_dir / "cad" / "input").mkdir(parents=True)
        (temp_dir / "cad" / "output").mkdir(parents=True)

        # Create some test files
        (temp_dir / "data" / "test.geojson").write_text('{"type": "FeatureCollection", "features": []}')
        (temp_dir / "config" / "settings.yaml").write_text("test: true")

        yield temp_dir
    finally:
        shutil.rmtree(temp_dir)


@pytest.fixture
def sample_project_aliases() -> ProjectPathAliases:
    """Create sample project aliases for testing."""
    return ProjectPathAliases(aliases={
        "data": {
            "input": "data/input",
            "output": "data/output",
            "test": "data/test.geojson"
        },
        "config": {
            "main": "config/main.yaml",
            "styles": "config/styles.yaml"
        },
        "cad": {
            "input": {
                "dwg": "cad/input/drawings",
                "dxf": "cad/input/dxf_files"
            },
            "output": "cad/output"
        },
        "temp": "temp/files"
    })


@pytest.fixture
def sample_path_context(sample_project_aliases: ProjectPathAliases, temp_project_dir: Path) -> PathResolutionContext:
    """Create sample path resolution context for testing."""
    return PathResolutionContext(
        project_name="test_project",
        project_root=str(temp_project_dir),
        aliases=sample_project_aliases
    )


@pytest.fixture
def complex_nested_aliases() -> ProjectPathAliases:
    """Create complex nested aliases for advanced testing."""
    return ProjectPathAliases(aliases={
        "environments": {
            "dev": {
                "data": "env/dev/data",
                "config": "env/dev/config",
                "output": "env/dev/output",
                "logs": "env/dev/logs"
            },
            "staging": {
                "data": "env/staging/data",
                "config": "env/staging/config",
                "output": "env/staging/output",
                "logs": "env/staging/logs"
            },
            "prod": {
                "data": "env/prod/data",
                "config": "env/prod/config",
                "output": "env/prod/output",
                "logs": "env/prod/logs"
            }
        },
        "shared": {
            "templates": "shared/templates",
            "styles": "shared/styles",
            "resources": {
                "fonts": "shared/resources/fonts",
                "images": "shared/resources/images",
                "icons": "shared/resources/icons"
            }
        },
        "tools": {
            "scripts": "tools/scripts",
            "utilities": "tools/utilities",
            "validators": "tools/validators"
        }
    })


# Test markers for easy test selection
pytest_plugins = []

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names and paths."""
    for item in items:
        # Add slow marker to tests that might be slow
        if "slow" in item.name or "benchmark" in item.name:
            item.add_marker(pytest.mark.slow)

        # Add integration marker to integration test files
        if "integration" in str(item.fspath) or "test_integration" in item.name:
            item.add_marker(pytest.mark.integration)

        # Add filesystem marker to tests that use temp directories
        if "temp_project_dir" in item.fixturenames or "filesystem" in item.name:
            item.add_marker(pytest.mark.filesystem)


# Custom assertions for domain models
class DomainAssertions:
    """Custom assertions for domain model testing."""

    @staticmethod
    def assert_valid_alias_name(name: str) -> None:
        """Assert that an alias name is valid according to domain rules."""
        import re
        assert name, "Alias name cannot be empty"
        assert re.match(r'^[a-zA-Z0-9._-]+$', name), f"Invalid alias name format: {name}"
        assert not name.startswith('.'), f"Alias name cannot start with dot: {name}"
        assert not name.endswith('.'), f"Alias name cannot end with dot: {name}"
        assert '..' not in name, f"Alias name cannot contain consecutive dots: {name}"

    @staticmethod
    def assert_valid_relative_path(path: str) -> None:
        """Assert that a path is valid and relative according to domain rules."""
        assert path, "Path cannot be empty"
        assert not path.startswith('/'), f"Path must be relative: {path}"
        assert not (len(path) > 1 and path[1] == ':'), f"Path must be relative: {path}"
        assert '..' not in path, f"Path cannot contain '..': {path}"


@pytest.fixture
def domain_assertions() -> DomainAssertions:
    """Provide domain-specific assertions for tests."""
    return DomainAssertions()
