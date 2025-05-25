"""Path resolution service implementation."""
import os
from typing import Optional, Dict, List
from ..interfaces.path_resolver_interface import IPathResolver
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.path_models import ProjectPathAliases, PathResolutionContext
from ..domain.exceptions import PathResolutionError


class PathResolverService(IPathResolver):
    """Service for resolving hierarchical path aliases within project contexts."""

    # Context-aware extension mappings
    CONTEXT_EXTENSIONS = {
        'geojsonFile': ['.geojson', '.json'],
        'stylePresetsFile': ['.yaml', '.yml'],
        'dxfFilename': ['.dxf'],
        'configFile': ['.yaml', '.yml', '.json'],
        'legendsFile': ['.yaml', '.yml'],
        'customStylesFile': ['.yaml', '.yml'],
        'geomLayersFile': ['.yaml', '.yml'],
        'shapeFile': ['.shp'],
        'csvFile': ['.csv'],
        'txtFile': ['.txt'],
        'xmlFile': ['.xml'],
        'jsonFile': ['.json'],
        'yamlFile': ['.yaml', '.yml']
    }

    def __init__(self, logger_service: ILoggingService):
        """Initialize with required injected dependencies."""
        self._logger = logger_service.get_logger(__name__)

    def create_context(
        self,
        project_name: str,
        project_root: str,
        aliases: ProjectPathAliases
    ) -> PathResolutionContext:
        """Create a path resolution context for a specific project."""
        self._logger.debug(f"Creating path resolution context for project: {project_name}")

        # Ensure project root is absolute
        if not os.path.isabs(project_root):
            project_root = os.path.abspath(project_root)

        return PathResolutionContext(
            project_name=project_name,
            project_root=project_root,
            aliases=aliases
        )

    def resolve_path(
        self,
        path_reference: str,
        context: PathResolutionContext,
        context_key: Optional[str] = None
    ) -> str:
        """Resolve a path reference to an absolute path."""
        if not path_reference:
            raise PathResolutionError(
                "Path reference cannot be empty",
                project_name=context.project_name
            )

        self._logger.debug(f"Resolving path reference: {path_reference} for project: {context.project_name}")

        # First resolve the basic path (alias or regular)
        if path_reference.startswith('@'):
            resolved_path = self._resolve_alias_path(path_reference, context)
        else:
            resolved_path = self._resolve_regular_path(path_reference, context)

        # Apply extension resolution if context_key is provided
        if context_key:
            resolved_path = self._resolve_with_context_extensions(resolved_path, context_key, context)

        return resolved_path

    def resolve_path_with_extensions(
        self,
        path_reference: str,
        context: PathResolutionContext,
        extension_list: List[str]
    ) -> str:
        """Resolve a path reference with explicit extension list."""
        if not path_reference:
            raise PathResolutionError(
                "Path reference cannot be empty",
                project_name=context.project_name
            )

        # First resolve the basic path
        if path_reference.startswith('@'):
            resolved_path = self._resolve_alias_path(path_reference, context)
        else:
            resolved_path = self._resolve_regular_path(path_reference, context)

        # Apply extension resolution with provided list
        resolved_path = self._resolve_with_extension_list(resolved_path, extension_list, context)

        return resolved_path

    def get_context_extensions(self, context_key: str) -> List[str]:
        """Get the list of extensions for a given context key."""
        return self.CONTEXT_EXTENSIONS.get(context_key, [])

    def resolve_alias_only(
        self,
        alias_reference: str,
        context: PathResolutionContext
    ) -> Optional[str]:
        """Resolve only alias references, returning None for non-alias paths."""
        if not alias_reference.startswith('@'):
            return None

        try:
            return self._resolve_alias_path(alias_reference, context)
        except PathResolutionError:
            return None

    def list_available_aliases(
        self,
        context: PathResolutionContext,
        prefix_filter: Optional[str] = None
    ) -> Dict[str, str]:
        """List all available aliases in the given context."""
        self._logger.debug(f"Listing aliases for project: {context.project_name}, prefix: {prefix_filter}")

        if prefix_filter:
            aliases = context.aliases.get_aliases_by_prefix(prefix_filter)
        else:
            aliases = context.aliases.list_aliases()

        # Convert to absolute paths
        result = {}
        for alias_name, path in aliases.items():
            if os.path.isabs(path):
                absolute_path = path
            else:
                absolute_path = os.path.join(context.project_root, path)
            result[alias_name] = absolute_path

        return result

    def validate_alias_reference(self, alias_reference: str) -> bool:
        """Validate if a string is a properly formatted alias reference."""
        if not alias_reference:
            return False

        if not alias_reference.startswith('@'):
            return False

        # Extract just the alias part (before any file path)
        alias_part, _ = self.extract_file_path_from_alias_reference(alias_reference)

        # Remove @ prefix for validation
        alias_name = alias_part[1:]

        # Use the same validation logic as HierarchicalAlias
        import re
        if not re.match(r'^[a-zA-Z0-9._-]+$', alias_name):
            return False

        if alias_name.startswith('.') or alias_name.endswith('.'):
            return False

        if '..' in alias_name:
            return False

        return True

    def extract_file_path_from_alias_reference(
        self,
        alias_reference: str
    ) -> tuple[str, Optional[str]]:
        """Extract alias and file path components from a full alias reference."""
        if not alias_reference.startswith('@'):
            raise PathResolutionError(f"Not an alias reference: {alias_reference}")

        # Find the first '/' after the '@' to separate alias from file path
        slash_index = alias_reference.find('/', 1)  # Start search after '@'

        if slash_index == -1:
            # No file path, just alias
            return alias_reference, None
        else:
            # Split into alias and file path
            alias_part = alias_reference[:slash_index]
            file_path_part = alias_reference[slash_index + 1:]
            return alias_part, file_path_part if file_path_part else None

    def _resolve_alias_path(self, alias_reference: str, context: PathResolutionContext) -> str:
        """Resolve an alias reference to an absolute path."""
        if not self.validate_alias_reference(alias_reference):
            raise PathResolutionError(
                f"Invalid alias reference format: {alias_reference}",
                alias_reference=alias_reference,
                project_name=context.project_name
            )

        # Extract alias and file path components
        alias_part, file_path_part = self.extract_file_path_from_alias_reference(alias_reference)

        # Resolve the alias part using the context
        resolved_alias_path = context.resolve_alias(alias_part)

        if resolved_alias_path is None:
            raise PathResolutionError(
                f"Alias not found: {alias_part}",
                alias_reference=alias_reference,
                project_name=context.project_name
            )

        # If there's a file path component, append it
        if file_path_part:
            final_path = os.path.join(resolved_alias_path, file_path_part)
        else:
            final_path = resolved_alias_path

        self._logger.debug(f"Resolved alias {alias_reference} to: {final_path}")
        return final_path

    def _resolve_regular_path(self, path_reference: str, context: PathResolutionContext) -> str:
        """Resolve a regular relative path to an absolute path."""
        # Security check - prevent directory traversal
        if '..' in path_reference:
            raise PathResolutionError(
                f"Path contains '..' which is not allowed for security reasons: {path_reference}",
                project_name=context.project_name
            )

        # Resolve relative to project root
        absolute_path = os.path.join(context.project_root, path_reference)
        absolute_path = os.path.normpath(absolute_path)

        self._logger.debug(f"Resolved regular path {path_reference} to: {absolute_path}")
        return absolute_path

    def _resolve_with_context_extensions(
        self,
        resolved_path: str,
        context_key: str,
        context: PathResolutionContext
    ) -> str:
        """Apply context-aware extension resolution to a resolved path."""
        extension_list = self.get_context_extensions(context_key)
        if not extension_list:
            self._logger.debug(f"No extensions defined for context key: {context_key}")
            return resolved_path

        return self._resolve_with_extension_list(resolved_path, extension_list, context)

    def _resolve_with_extension_list(
        self,
        resolved_path: str,
        extension_list: List[str],
        context: PathResolutionContext
    ) -> str:
        """Apply extension resolution using provided extension list."""
        # If path already has an extension, return as-is
        if os.path.splitext(resolved_path)[1]:
            self._logger.debug(f"Path already has extension: {resolved_path}")
            return resolved_path

        # Try each extension in order
        for extension in extension_list:
            candidate_path = resolved_path + extension
            if os.path.exists(candidate_path):
                self._logger.debug(f"Found file with extension {extension}: {candidate_path}")
                return candidate_path

        # If no files found with any extension, return original path
        # This allows for graceful handling of missing files
        self._logger.debug(f"No files found with extensions {extension_list}, returning original: {resolved_path}")
        return resolved_path
