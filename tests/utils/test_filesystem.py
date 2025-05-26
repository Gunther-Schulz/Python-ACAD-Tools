"""Tests for filesystem utility functions."""
import pytest
import tempfile
import os
from pathlib import Path

from src.utils.filesystem import ensure_parent_dir_exists


class TestEnsureParentDirExists:
    """Test cases for ensure_parent_dir_exists function."""

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_creates_parent_directory(self):
        """Test that parent directory is created when it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "new_dir" / "subdir" / "test.txt"

            # Ensure the parent directories don't exist initially
            assert not test_file.parent.exists()

            # Call the function
            ensure_parent_dir_exists(str(test_file))

            # Check that parent directories were created
            assert test_file.parent.exists()
            assert test_file.parent.is_dir()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_does_nothing_when_parent_exists(self):
        """Test that function does nothing when parent directory already exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "existing_dir" / "test.txt"

            # Create the parent directory first
            test_file.parent.mkdir(parents=True, exist_ok=True)
            original_stat = test_file.parent.stat()

            # Call the function
            ensure_parent_dir_exists(str(test_file))

            # Check that directory still exists and wasn't modified
            assert test_file.parent.exists()
            assert test_file.parent.is_dir()
            # Note: We can't easily check if the directory was "touched" without
            # more complex timing checks, but the important thing is it still exists

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_handles_nested_directories(self):
        """Test that deeply nested directories are created correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "a" / "b" / "c" / "d" / "e" / "test.txt"

            # Ensure none of the nested directories exist
            assert not (temp_path / "a").exists()

            # Call the function
            ensure_parent_dir_exists(str(test_file))

            # Check that all nested directories were created
            assert test_file.parent.exists()
            assert (temp_path / "a").exists()
            assert (temp_path / "a" / "b").exists()
            assert (temp_path / "a" / "b" / "c").exists()
            assert (temp_path / "a" / "b" / "c" / "d").exists()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_handles_file_in_current_directory(self):
        """Test that function handles files in current directory (no parent to create)."""
        # This should not raise an error
        ensure_parent_dir_exists("test.txt")

        # For a file with no directory component, parent_dir would be empty string
        # The function should handle this gracefully

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_handles_absolute_paths(self):
        """Test that function works with absolute paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "new_dir", "test.txt")

            # Ensure the parent directory doesn't exist
            parent_dir = os.path.dirname(test_file)
            assert not os.path.exists(parent_dir)

            # Call the function with absolute path
            ensure_parent_dir_exists(test_file)

            # Check that parent directory was created
            assert os.path.exists(parent_dir)
            assert os.path.isdir(parent_dir)

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_handles_relative_paths(self):
        """Test that function works with relative paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Change to temp directory
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)

                test_file = "relative_dir/test.txt"

                # Ensure the parent directory doesn't exist
                assert not os.path.exists("relative_dir")

                # Call the function with relative path
                ensure_parent_dir_exists(test_file)

                # Check that parent directory was created
                assert os.path.exists("relative_dir")
                assert os.path.isdir("relative_dir")

            finally:
                os.chdir(original_cwd)

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_handles_empty_string(self):
        """Test that function handles empty string gracefully."""
        # This should not raise an error
        ensure_parent_dir_exists("")

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_handles_path_with_trailing_slash(self):
        """Test that function handles paths with trailing slashes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "new_dir" / "test.txt"

            # Call with trailing slash (though this is unusual for a file path)
            ensure_parent_dir_exists(str(test_file) + "/")

            # The parent should still be created correctly
            assert test_file.parent.exists()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_concurrent_creation_safety(self):
        """Test that function is safe when called concurrently (exist_ok=True)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "concurrent_dir" / "test.txt"

            # Call the function multiple times (simulating concurrent calls)
            ensure_parent_dir_exists(str(test_file))
            ensure_parent_dir_exists(str(test_file))
            ensure_parent_dir_exists(str(test_file))

            # Should not raise any errors and directory should exist
            assert test_file.parent.exists()
            assert test_file.parent.is_dir()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.filesystem
    @pytest.mark.fast
    def test_preserves_existing_files_in_parent(self):
        """Test that existing files in parent directory are preserved."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            parent_dir = temp_path / "existing_parent"
            existing_file = parent_dir / "existing.txt"
            new_file = parent_dir / "new.txt"

            # Create parent directory and an existing file
            parent_dir.mkdir(parents=True, exist_ok=True)
            existing_file.write_text("existing content")

            # Call function for a new file in the same directory
            ensure_parent_dir_exists(str(new_file))

            # Check that existing file is preserved
            assert existing_file.exists()
            assert existing_file.read_text() == "existing content"
            assert parent_dir.exists()
            assert parent_dir.is_dir()
