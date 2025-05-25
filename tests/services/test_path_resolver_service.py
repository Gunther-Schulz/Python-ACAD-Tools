"""Comprehensive tests for PathResolverService."""
import pytest
import os
from unittest.mock import Mock, patch
from pathlib import Path

from src.services.path_resolver_service import PathResolverService
from src.interfaces.logging_service_interface import ILoggingService
from src.domain.path_models import ProjectPathAliases, PathResolutionContext
from src.domain.exceptions import PathResolutionError


class TestPathResolverService:
    """Test cases for PathResolverService."""

    @pytest.fixture
    def mock_logger_service(self) -> Mock:
        """Create mock logging service."""
        mock_service = Mock(spec=ILoggingService)
        mock_logger = Mock()
        mock_service.get_logger.return_value = mock_logger
        return mock_service

    @pytest.fixture
    def path_resolver(self, mock_logger_service: Mock) -> PathResolverService:
        """Create PathResolverService instance with mocked dependencies."""
        return PathResolverService(mock_logger_service)

    @pytest.fixture
    def sample_aliases(self) -> ProjectPathAliases:
        """Create sample aliases for testing."""
        return ProjectPathAliases(aliases={
            "data": {
                "input": "data/input",
                "output": "data/output"
            },
            "config": "config/settings.yaml",
            "temp": "temp/files"
        })

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_service_initialization(self, mock_logger_service: Mock):
        """Test PathResolverService initialization."""
        service = PathResolverService(mock_logger_service)

        # Verify logger was requested
        mock_logger_service.get_logger.assert_called_once()

        # Verify service has expected attributes
        assert hasattr(service, '_logger')

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_create_context(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test creating path resolution context."""
        context = path_resolver.create_context(
            project_name="test_project",
            project_root="/path/to/project",
            aliases=sample_aliases
        )

        assert isinstance(context, PathResolutionContext)
        assert context.project_name == "test_project"
        assert context.project_root == "/path/to/project"
        assert context.aliases == sample_aliases

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_regular_path(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test resolving regular (non-alias) paths."""
        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        # Regular relative path
        result = path_resolver.resolve_path("data/file.txt", context)
        expected = os.path.join("/project/root", "data/file.txt")
        assert result == expected

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_alias_reference(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test resolving alias references."""
        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        # Simple alias
        result = path_resolver.resolve_path("@config", context)
        expected = os.path.join("/project/root", "config/settings.yaml")
        assert result == expected

        # Hierarchical alias
        result = path_resolver.resolve_path("@data.input", context)
        expected = os.path.join("/project/root", "data/input")
        assert result == expected

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_alias_with_additional_path(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test resolving alias references with additional path components."""
        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        # Alias with additional path
        result = path_resolver.resolve_path("@data.input/file.geojson", context)
        expected = os.path.join("/project/root", "data/input", "file.geojson")
        assert result == expected

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_nonexistent_alias(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test resolving nonexistent alias references."""
        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        with pytest.raises(PathResolutionError) as exc_info:
            path_resolver.resolve_path("@nonexistent", context)

        exc = exc_info.value
        assert "Alias 'nonexistent' not found" in str(exc)
        assert exc.alias_reference == "@nonexistent"
        assert exc.project_name == "test"

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_with_context_key_extension_resolution(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test resolving paths with context-aware extension resolution."""
        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        # Test with geojsonFile context - should try .geojson, .json extensions
        with patch('os.path.exists') as mock_exists:
            # First call (original path) returns False, second call (.geojson) returns True
            mock_exists.side_effect = [False, True]

            result = path_resolver.resolve_path("@data.input/test", context, context_key="geojsonFile")
            expected = os.path.join("/project/root", "data/input", "test.geojson")
            assert result == expected

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_with_context_key_no_extension_needed(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test resolving paths that already have extensions."""
        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        # Path already has extension - should not try to add more
        result = path_resolver.resolve_path("@data.input/test.geojson", context, context_key="geojsonFile")
        expected = os.path.join("/project/root", "data/input", "test.geojson")
        assert result == expected

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_with_unknown_context_key(self, path_resolver: PathResolverService, sample_aliases: ProjectPathAliases):
        """Test resolving paths with unknown context key."""
        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        # Unknown context key - should not try extension resolution
        result = path_resolver.resolve_path("@data.input/test", context, context_key="unknownFileType")
        expected = os.path.join("/project/root", "data/input", "test")
        assert result == expected

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.filesystem
    def test_try_extensions_file_exists(self, path_resolver: PathResolverService, tmp_path: Path):
        """Test extension resolution when files exist."""
        # Create test files
        test_file = tmp_path / "test.geojson"
        test_file.write_text('{"test": true}')

        base_path = str(tmp_path / "test")
        extensions = [".geojson", ".json"]

        result = path_resolver._try_extensions(base_path, extensions)
        assert result == str(test_file)

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.filesystem
    def test_try_extensions_no_file_exists(self, path_resolver: PathResolverService, tmp_path: Path):
        """Test extension resolution when no files exist."""
        base_path = str(tmp_path / "nonexistent")
        extensions = [".geojson", ".json"]

        result = path_resolver._try_extensions(base_path, extensions)
        assert result == base_path  # Returns original path if no files found

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_try_extensions_empty_extensions(self, path_resolver: PathResolverService):
        """Test extension resolution with empty extensions list."""
        base_path = "/some/path"
        extensions = []

        result = path_resolver._try_extensions(base_path, extensions)
        assert result == base_path

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_get_extensions_for_context(self, path_resolver: PathResolverService):
        """Test getting extensions for different context keys."""
        # Test known context keys
        assert path_resolver._get_extensions_for_context("geojsonFile") == [".geojson", ".json"]
        assert path_resolver._get_extensions_for_context("stylePresetsFile") == [".yaml", ".yml"]
        assert path_resolver._get_extensions_for_context("dxf.outputPath") == [".dxf"]

        # Test unknown context key
        assert path_resolver._get_extensions_for_context("unknownType") == []

    @pytest.mark.integration
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.filesystem
    def test_full_resolution_workflow(self, path_resolver: PathResolverService, tmp_path: Path):
        """Test complete path resolution workflow with real filesystem."""
        # Create project structure
        project_root = tmp_path / "project"
        project_root.mkdir()

        data_dir = project_root / "data" / "input"
        data_dir.mkdir(parents=True)

        config_dir = project_root / "config"
        config_dir.mkdir()

        # Create test files
        geojson_file = data_dir / "test.geojson"
        geojson_file.write_text('{"type": "FeatureCollection", "features": []}')

        config_file = config_dir / "settings.yaml"
        config_file.write_text("test: true")

        # Create aliases
        aliases = ProjectPathAliases(aliases={
            "data": {
                "input": "data/input",
                "output": "data/output"
            },
            "config": "config/settings.yaml"
        })

        # Create context
        context = path_resolver.create_context(
            project_name="integration_test",
            project_root=str(project_root),
            aliases=aliases
        )

        # Test various resolutions
        # Direct file reference
        result = path_resolver.resolve_path("@config", context)
        assert result == str(config_file)
        assert Path(result).exists()

        # Directory alias with file
        result = path_resolver.resolve_path("@data.input/test.geojson", context)
        assert result == str(geojson_file)
        assert Path(result).exists()

        # Extension resolution
        result = path_resolver.resolve_path("@data.input/test", context, context_key="geojsonFile")
        assert result == str(geojson_file)
        assert Path(result).exists()

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_error_handling_and_logging(self, mock_logger_service: Mock, sample_aliases: ProjectPathAliases):
        """Test error handling and logging behavior."""
        path_resolver = PathResolverService(mock_logger_service)
        mock_logger = mock_logger_service.get_logger.return_value

        context = PathResolutionContext(
            project_name="test",
            project_root="/project/root",
            aliases=sample_aliases
        )

        # Test error logging for nonexistent alias
        with pytest.raises(PathResolutionError):
            path_resolver.resolve_path("@nonexistent", context)

        # Verify error was logged
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert "Alias 'nonexistent' not found" in error_call

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_interface_compliance(self, path_resolver: PathResolverService):
        """Test that PathResolverService implements IPathResolver interface correctly."""
        from src.interfaces.path_resolver_interface import IPathResolver

        # Verify service has all required methods
        assert hasattr(path_resolver, 'create_context')
        assert hasattr(path_resolver, 'resolve_path')
        assert hasattr(path_resolver, '_try_extensions')
        assert hasattr(path_resolver, '_get_extensions_for_context')

        # Verify method signatures match interface
        import inspect

        # Check create_context signature
        create_context_sig = inspect.signature(path_resolver.create_context)
        expected_params = ['project_name', 'project_root', 'aliases']
        actual_params = list(create_context_sig.parameters.keys())
        assert actual_params == expected_params

        # Check resolve_path signature
        resolve_path_sig = inspect.signature(path_resolver.resolve_path)
        expected_params = ['path_reference', 'context', 'context_key']
        actual_params = list(resolve_path_sig.parameters.keys())
        assert actual_params == expected_params


class TestPathResolverServiceEdgeCases:
    """Test edge cases and error conditions for PathResolverService."""

    @pytest.fixture
    def path_resolver(self) -> PathResolverService:
        """Create PathResolverService with minimal mock."""
        mock_logger_service = Mock(spec=ILoggingService)
        mock_logger_service.get_logger.return_value = Mock()
        return PathResolverService(mock_logger_service)

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_empty_reference(self, path_resolver: PathResolverService):
        """Test resolving empty path reference."""
        aliases = ProjectPathAliases()
        context = PathResolutionContext(
            project_name="test",
            project_root="/root",
            aliases=aliases
        )

        result = path_resolver.resolve_path("", context)
        assert result == "/root"

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_just_at_symbol(self, path_resolver: PathResolverService):
        """Test resolving path that is just '@' symbol."""
        aliases = ProjectPathAliases()
        context = PathResolutionContext(
            project_name="test",
            project_root="/root",
            aliases=aliases
        )

        with pytest.raises(PathResolutionError) as exc_info:
            path_resolver.resolve_path("@", context)

        assert "Invalid alias reference" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_resolve_path_malformed_alias(self, path_resolver: PathResolverService):
        """Test resolving malformed alias references."""
        aliases = ProjectPathAliases()
        context = PathResolutionContext(
            project_name="test",
            project_root="/root",
            aliases=aliases
        )

        malformed_aliases = ["@", "@.", "@..", "@/invalid"]

        for alias in malformed_aliases:
            with pytest.raises(PathResolutionError):
                path_resolver.resolve_path(alias, context)

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_context_creation_with_empty_aliases(self, path_resolver: PathResolverService):
        """Test creating context with empty aliases."""
        empty_aliases = ProjectPathAliases()

        context = path_resolver.create_context(
            project_name="test",
            project_root="/root",
            aliases=empty_aliases
        )

        assert context.project_name == "test"
        assert context.project_root == "/root"
        assert context.aliases.list_aliases() == {}

    @pytest.mark.unit
    @pytest.mark.services
    @pytest.mark.path_resolution
    @pytest.mark.fast
    def test_extension_resolution_priority(self, path_resolver: PathResolverService, tmp_path: Path):
        """Test that extension resolution respects priority order."""
        # Create files with different extensions
        (tmp_path / "test.json").write_text('{"json": true}')
        (tmp_path / "test.geojson").write_text('{"geojson": true}')

        base_path = str(tmp_path / "test")
        extensions = [".geojson", ".json"]  # .geojson should be tried first

        result = path_resolver._try_extensions(base_path, extensions)
        assert result.endswith("test.geojson")  # Should find .geojson first
