import os
from typing import Optional, List
from logging import Logger

# This import is not strictly needed by the service itself if it only uses Logger,
# but good for type hinting consistency if ProjectConfig instances are ever passed
# directly or used in related services that might call this.
# from dxfplanner.config.schemas import ProjectConfig

class FontProviderServiceError(Exception):
    """Custom exception for FontProviderService errors."""
    pass

class FontProviderService:
    """
    Resolves font names to their full file paths based on a list of search directories.
    """
    COMMON_FONT_EXTENSIONS = [".ttf", ".otf"]

    def __init__(self, font_directories: List[str], logger: Logger):
        """
        Initializes the FontProviderService.

        Args:
            font_directories: A list of absolute paths to directories where fonts should be searched.
            logger: An instance of Logger.
        """
        self.font_directories = font_directories
        self.logger = logger
        if not font_directories:
            self.logger.info("FontProviderService initialized with no font directories.")

    def get_font_path(self, font_name: Optional[str]) -> Optional[str]:
        """
        Finds the full path to a font file.

        Searches for the font_name (with and without common extensions)
        in the configured font_directories.

        Args:
            font_name: The name of the font (e.g., "arial.ttf" or "arial").

        Returns:
            The absolute path to the font file if found, otherwise None.
        """
        if not font_name:
            self.logger.debug("get_font_path called with no font_name, returning None.")
            return None

        if not self.font_directories:
            self.logger.debug(f"No font directories configured, cannot find font '{font_name}'.")
            return None

        self.logger.debug(f"Searching for font '{font_name}' in directories: {self.font_directories}")

        potential_filenames = [font_name]
        # If font_name has no extension, add common ones to the search list
        if not os.path.splitext(font_name)[1]:
            potential_filenames.extend([font_name + ext for ext in self.COMMON_FONT_EXTENSIONS])

        # Remove duplicates that could arise if font_name was e.g. "arial.ttf" and ".ttf" is in COMMON_FONT_EXTENSIONS
        # (though current logic for adding extensions only if font_name has no ext. already prevents this specific case)
        # More robustly, ensure font_name itself is checked first if it has an extension,
        # or check permutations. The current list `potential_filenames` will prioritize the exact font_name.
        # A simple unique list:
        # potential_filenames = list(dict.fromkeys(potential_filenames)) # Python 3.7+ for ordered unique list

        for directory in self.font_directories:
            for name_to_check in potential_filenames:
                full_path = os.path.join(directory, name_to_check)
                # Ensure the path is normalized, especially if directories might have trailing slashes
                # or font_name might have leading slashes (though less likely for a name)
                normalized_path = os.path.normpath(full_path)
                if os.path.exists(normalized_path) and os.path.isfile(normalized_path):
                    self.logger.info(f"Font '{font_name}' (checked as '{name_to_check}') found at '{normalized_path}'.")
                    return normalized_path

        self.logger.warning(f"Font '{font_name}' not found in any of the specified directories after checking variants: {potential_filenames}.")
        return None
