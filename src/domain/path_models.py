"""Path resolution domain models following PROJECT_ARCHITECTURE.MD specification."""
from typing import Dict, Any, Optional, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
import re


class HierarchicalAlias(BaseModel):
    """Represents a single hierarchical alias definition with dot notation support."""
    model_config = ConfigDict(frozen=True, extra='forbid')

    name: str = Field(..., description="The alias name (e.g., 'cad.input', 'survey.raw')")
    path: str = Field(..., description="The relative path this alias resolves to")
    description: Optional[str] = Field(None, description="Optional description of this alias")

    @field_validator('name')
    @classmethod
    def validate_alias_name(cls, v: str) -> str:
        """Validate alias name follows hierarchical dot notation rules."""
        if not v:
            raise ValueError("Alias name cannot be empty")

        # Allow alphanumeric, dots, underscores, hyphens
        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError("Alias name can only contain alphanumeric characters, dots, underscores, and hyphens")

        # Cannot start or end with dot
        if v.startswith('.') or v.endswith('.'):
            raise ValueError("Alias name cannot start or end with a dot")

        # Cannot have consecutive dots
        if '..' in v:
            raise ValueError("Alias name cannot contain consecutive dots")

        return v

    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate path is relative and safe."""
        if not v:
            raise ValueError("Path cannot be empty")

        # Ensure relative path (no absolute paths)
        if v.startswith('/') or (len(v) > 1 and v[1] == ':'):
            raise ValueError("Path must be relative, not absolute")

        # Prevent directory traversal attacks
        if '..' in v:
            raise ValueError("Path cannot contain '..' for security reasons")

        return v


class ProjectPathAliases(BaseModel):
    """Collection of hierarchical path aliases for a project."""
    model_config = ConfigDict(extra='forbid')

    aliases: Dict[str, Union[str, Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Hierarchical alias definitions using dot notation"
    )

    @model_validator(mode='after')
    def validate_aliases_structure(self) -> 'ProjectPathAliases':
        """Validate the hierarchical alias structure and convert to flat representation."""
        if not self.aliases:
            return self

        # Flatten nested dictionary structure to dot notation
        flattened = self._flatten_aliases(self.aliases)

        # Validate each flattened alias
        validated_aliases = {}
        for name, path in flattened.items():
            if not isinstance(path, str):
                raise ValueError(f"Alias '{name}' must resolve to a string path, got {type(path)}")

            # Create HierarchicalAlias for validation
            alias = HierarchicalAlias(name=name, path=path)
            validated_aliases[alias.name] = alias.path

        # Check for circular references
        self._check_circular_references(validated_aliases)

        # Store the validated flat structure
        object.__setattr__(self, 'aliases', validated_aliases)
        return self

    def _flatten_aliases(self, aliases_dict: Dict[str, Any], prefix: str = '') -> Dict[str, str]:
        """Recursively flatten nested alias dictionary to dot notation."""
        flattened = {}

        for key, value in aliases_dict.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                # Recursively flatten nested structure
                flattened.update(self._flatten_aliases(value, full_key))
            elif isinstance(value, str):
                # Leaf node - this is a path
                flattened[full_key] = value
            else:
                raise ValueError(f"Invalid alias value for '{full_key}': must be string or nested dict")

        return flattened

    def _check_circular_references(self, aliases: Dict[str, str]) -> None:
        """Check for circular references in alias definitions."""
        # For now, we don't support alias-to-alias resolution, so no circular references possible
        # This method is a placeholder for future enhancement
        pass

    def get_alias_path(self, alias_name: str) -> Optional[str]:
        """Get the path for a given alias name."""
        return self.aliases.get(alias_name)

    def list_aliases(self) -> Dict[str, str]:
        """Get all aliases as a flat dictionary."""
        return self.aliases.copy()

    def get_aliases_by_prefix(self, prefix: str) -> Dict[str, str]:
        """Get all aliases that start with the given prefix."""
        return {
            name: path for name, path in self.aliases.items()
            if name.startswith(f"{prefix}.")
        }


class PathResolutionContext(BaseModel):
    """Context information for path resolution operations."""
    model_config = ConfigDict(frozen=True)

    project_name: str = Field(..., description="Name of the current project")
    project_root: str = Field(..., description="Root directory of the project")
    aliases: ProjectPathAliases = Field(..., description="Available path aliases for this project")

    def resolve_alias(self, alias_reference: str) -> Optional[str]:
        """
        Resolve an alias reference to an absolute path.

        Args:
            alias_reference: Reference like '@cad.input' or '@survey.raw'

        Returns:
            Absolute path if alias exists, None otherwise
        """
        if not alias_reference.startswith('@'):
            return None

        alias_name = alias_reference[1:]  # Remove '@' prefix
        relative_path = self.aliases.get_alias_path(alias_name)

        if relative_path is None:
            return None

        # Combine project root with relative path
        import os
        return os.path.join(self.project_root, relative_path)
