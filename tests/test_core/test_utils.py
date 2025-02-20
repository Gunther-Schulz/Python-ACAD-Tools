"""Tests for core utility functions."""

import os
import logging
import pytest
from pathlib import Path
from src.core.utils import (
    resolve_path,
    ensure_directory,
    validate_file_exists,
    get_file_extension,
    setup_logger
)

def test_resolve_path():
    """Test path resolution with and without prefix."""
    # Test without prefix
    assert resolve_path("test/path") == os.path.normpath("test/path")
    
    # Test with prefix
    prefix = "prefix/dir"
    expected = os.path.normpath("prefix/dir/test/path")
    assert resolve_path("test/path", prefix) == expected
    
    # Test empty path
    assert resolve_path("") == ""
    
    # Test None path
    assert resolve_path(None) is None

def test_ensure_directory(temp_dir):
    """Test directory creation."""
    test_dir = os.path.join(temp_dir, "test_dir")
    
    # Test directory creation
    ensure_directory(test_dir)
    assert os.path.exists(test_dir)
    assert os.path.isdir(test_dir)
    
    # Test idempotency (should not raise when directory exists)
    ensure_directory(test_dir)
    assert os.path.exists(test_dir)

def test_validate_file_exists(temp_dir):
    """Test file existence validation."""
    test_file = os.path.join(temp_dir, "test.txt")
    
    # Test non-existent file
    assert not validate_file_exists(test_file)
    
    # Create file and test again
    with open(test_file, 'w') as f:
        f.write("test")
    assert validate_file_exists(test_file)

def test_get_file_extension():
    """Test file extension extraction."""
    assert get_file_extension("test.txt") == ".txt"
    assert get_file_extension("path/to/test.DXF") == ".dxf"
    assert get_file_extension("no_extension") == ""
    assert get_file_extension(".hidden") == ""
    assert get_file_extension("multiple.dots.txt") == ".txt"

def test_setup_logger(temp_dir):
    """Test logger setup and configuration."""
    logger_name = "test_logger"
    log_file = os.path.join(temp_dir, "test.log")
    
    # Test logger without file
    logger = setup_logger(logger_name)
    assert logger.name == logger_name
    assert logger.level == logging.INFO
    assert not logger.handlers  # No file handler
    
    # Test logger with file
    logger_with_file = setup_logger(logger_name + "_file", log_file)
    assert logger_with_file.name == logger_name + "_file"
    assert len(logger_with_file.handlers) == 1
    assert isinstance(logger_with_file.handlers[0], logging.FileHandler)
    
    # Test logging to file
    test_message = "Test log message"
    logger_with_file.info(test_message)
    
    with open(log_file, 'r') as f:
        log_content = f.read()
        assert test_message in log_content 