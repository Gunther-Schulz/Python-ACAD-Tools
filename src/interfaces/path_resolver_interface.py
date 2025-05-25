"""Interface for path resolution services."""
from typing import Protocol, Optional, Dict, List
from ..domain.path_models import ProjectPathAliases, PathResolutionContext


class IPathResolver(Protocol):
    """Interface for resolving hierarchical path aliases within project contexts."""

    def create_context(
        self,
        project_name: str,
        project_root: str,
        aliases: ProjectPathAliases
    ) -> PathResolutionContext:
        """
        Create a path resolution context for a specific project.

        Args:
            project_name: Name of the project
            project_root: Root directory path of the project
            aliases: Project-specific path aliases

        Returns:
            PathResolutionContext for the project
        """
        ...

    def resolve_path(
        self,
        path_reference: str,
        context: PathResolutionContext,
        context_key: Optional[str] = None
    ) -> str:
        """
        Resolve a path reference to an absolute path.

        Args:
            path_reference: Either an alias reference (e.g., '@cad.input/file.dxf')
                          or a regular relative path
            context: Path resolution context for the current project
            context_key: Optional context key for extension resolution (e.g., 'geojsonFile', 'stylePresetsFile')
                        If provided and path has no extension, will try appropriate extensions

        Returns:
            Absolute path. If path_reference is an alias, resolves the alias first.
            If path_reference is a regular path, resolves relative to project root.
            If context_key is provided and resolved path has no extension, tries context-appropriate extensions.

        Raises:
            PathResolutionError: If alias cannot be resolved or path is invalid
        """
        ...

    def resolve_alias_only(
        self,
        alias_reference: str,
        context: PathResolutionContext
    ) -> Optional[str]:
        """
        Resolve only alias references, returning None for non-alias paths.

        Args:
            alias_reference: Alias reference like '@cad.input' or '@survey.raw'
            context: Path resolution context for the current project

        Returns:
            Absolute path if alias exists, None if not an alias or alias not found
        """
        ...

    def list_available_aliases(
        self,
        context: PathResolutionContext,
        prefix_filter: Optional[str] = None
    ) -> Dict[str, str]:
        """
        List all available aliases in the given context.

        Args:
            context: Path resolution context for the current project
            prefix_filter: Optional prefix to filter aliases (e.g., 'cad' for 'cad.*')

        Returns:
            Dictionary mapping alias names to their resolved absolute paths
        """
        ...

    def validate_alias_reference(
        self,
        alias_reference: str
    ) -> bool:
        """
        Validate if a string is a properly formatted alias reference.

        Args:
            alias_reference: String to validate (e.g., '@cad.input')

        Returns:
            True if properly formatted alias reference, False otherwise
        """
        ...

    def extract_file_path_from_alias_reference(
        self,
        alias_reference: str
    ) -> tuple[str, Optional[str]]:
        """
        Extract alias and file path components from a full alias reference.

        Args:
            alias_reference: Full reference like '@cad.input/file.dxf' or '@survey.raw'

        Returns:
            Tuple of (alias_part, file_path_part).
            For '@cad.input/file.dxf' returns ('@cad.input', 'file.dxf')
            For '@cad.input' returns ('@cad.input', None)
        """
        ...

    def resolve_path_with_extensions(
        self,
        path_reference: str,
        context: PathResolutionContext,
        extension_list: List[str]
    ) -> str:
        """
        Resolve a path reference with explicit extension list.

        Args:
            path_reference: Either an alias reference or regular relative path
            context: Path resolution context for the current project
            extension_list: List of extensions to try (e.g., ['.geojson', '.json'])

        Returns:
            Absolute path with appropriate extension applied if needed

        Raises:
            PathResolutionError: If alias cannot be resolved or path is invalid
        """
        ...

    def get_context_extensions(
        self,
        context_key: str
    ) -> List[str]:
        """
        Get the list of extensions for a given context key.

        Args:
            context_key: Context key like 'geojsonFile', 'stylePresetsFile'

        Returns:
            List of extensions to try for this context (e.g., ['.geojson', '.json'])
        """
        ...
