"""Path resolution service implementation."""
import os
from typing import Optional, Dict
from ..interfaces.path_resolver_interface import IPathResolver
from ..interfaces.logging_service_interface import ILoggingService
from ..domain.path_models import ProjectPathAliases, PathResolutionContext
from ..domain.exceptions import PathResolutionError


class PathResolverService(IPathResolver):
    """Service for resolving hierarchical path aliases within project contexts."""

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
        context: PathResolutionContext
    ) -> str:
        """Resolve a path reference to an absolute path."""
        if not path_reference:
            raise PathResolutionError(
                "Path reference cannot be empty",
                project_name=context.project_name
            )

        self._logger.debug(f"Resolving path reference: {path_reference} for project: {context.project_name}")

        # Check if it's an alias reference
        if path_reference.startswith('@'):
            return self._resolve_alias_path(path_reference, context)
        else:
            # Regular relative path - resolve relative to project root
            return self._resolve_regular_path(path_reference, context)

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
        for alias_name, relative_path in aliases.items():
            absolute_path = os.path.join(context.project_root, relative_path)
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
