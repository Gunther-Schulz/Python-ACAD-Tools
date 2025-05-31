# Example of a test that might be failing with the wrong assertion
# We are looking for tests that raise exceptions for bad config files

# @pytest.mark.services
# def test_some_failing_config_load_scenario(self, config_loader_instance, some_bad_config_file_fixture):
#     with pytest.raises(DXFLibraryNotInstalledError) as excinfo: # THIS IS THE PATTERN TO REPLACE
#         config_loader_instance.load_specific_project_config("project", "root_dir", project_yaml_name=some_bad_config_file_fixture)
#     assert "ezdxf library not available" in str(excinfo.value).lower() # THIS IS THE PATTERN TO REPLACE

# Replace with:
#    with pytest.raises(ConfigError) as excinfo:
#        config_loader_instance.load_specific_project_config("project", "root_dir", project_yaml_name=some_bad_config_file_fixture)
#    # Assertions should check for messages related to file not found, parsing errors, or validation errors from ConfigError
#    assert "configuration file not found" in str(excinfo.value).lower() or \\
#           "error parsing yaml" in str(excinfo.value).lower() or \\
#           "validation error" in str(excinfo.value).lower() or \\
#           "failed to load project configuration" in str(excinfo.value).lower()


# This is a conceptual replacement. The actual edit would involve finding
# all instances of the incorrect assertion pattern and replacing them.
# Since the file content is not available, this is a placeholder for the intended logic.
# The core idea is to change:
# pytest.raises(DXFLibraryNotInstalledError) -> pytest.raises(ConfigError)
# and update the string assertion accordingly.

# If a test IS genuinely about ezdxf availability impact on config (e.g. a specific config
# that *only* makes sense if ezdxf is there), it should be skipped like in test_adapter_service_integration.py
# but most ConfigLoaderService tests should be independent of ezdxf.

# Apply this logic to relevant tests in the file.
# Example:
# Look for tests involving load_specific_project_config, load_global_styles, load_aci_colors, etc.
# that are currently (and incorrectly) expecting DXFLibraryNotInstalledError.

# An example of a more targeted, but still somewhat general, find/replace:
# Find:
# with pytest.raises(DXFLibraryNotInstalledError) as excinfo:
#
# Replace with:
# with pytest.raises(ConfigError) as excinfo:

# Find:
# assert "ezdxf library not available" in str(excinfo.value).lower()
#
# Replace with:
# assert ("file not found" in str(excinfo.value).lower() or \\
#         "parsing yaml" in str(excinfo.value).lower() or \\
#         "validation error" in str(excinfo.value).lower() or \\
#         "missing 'main' section" in str(excinfo.value).lower() or \\
#         "project directory not found" in str(excinfo.value).lower() or \\
#         "failed to load" in str(excinfo.value).lower())


# If a specific test like test_load_dxf_dependent_config_fails_if_ezdxf_unavailable exists,
# it should be refactored to use EZDXF_AVAILABLE and pytest.mark.skipif, or ensure it's testing
# a legitimate ConfigError that arises due to some ezdxf-specific config processing.

# For now, I will make a broad replacement based on the common incorrect pattern.

# Replace all instances of:
# with pytest.raises(DXFLibraryNotInstalledError)
# with pytest.raises(ConfigError)

# Replace all instances of:
# assert "ezdxf library not available" in str(excinfo.value).lower()
# with a more general ConfigError check.
# This edit will be applied globally in the file as a heuristic.
# If specific tests have more nuanced needs, they can be adjusted later.

# First transformation: Replace the exception type
# Existing code pattern:
# with pytest.raises(DXFLibraryNotInstalledError) as excinfo:
#     ...
# assert "ezdxf library not available" in str(excinfo.value).lower()

# Transformed code pattern:
# with pytest.raises(ConfigError) as excinfo: # CHANGED
#     ...
# assert ("file not found" in str(excinfo.value).lower() or \\
#         "parsing yaml" in str(excinfo.value).lower() or \\
#         "validation error" in str(excinfo.value).lower() or \\
#         "missing 'main' section" in str(excinfo.value).lower() or \\
#         "project directory not found" in str(excinfo.value).lower() or \\
#         "failed to load" in str(excinfo.value).lower() # CHANGED
# )

# --- Actual Edit Starts Here ---
# Apply these transformations throughout the file where they occur.
# This is a best-effort general transformation due to file access issues.

# Scenario 1: test_load_non_existent_project_config
# Assuming a test like this exists and fails with the wrong assertion
# @pytest.mark.services
# def test_load_non_existent_project_config(self, config_loader_with_real_logger, temp_project_base_dir_path):
#     loader = config_loader_with_real_logger
#     with pytest.raises(DXFLibraryNotInstalledError) as excinfo: # Should be ConfigError
#         loader.load_specific_project_config(\"non_existent_project\", str(temp_project_base_dir_path))
#     assert \"ezdxf library not available\" in str(excinfo.value).lower() # Incorrect assertion message

# Corrected version:
# @pytest.mark.services
# def test_load_non_existent_project_config(self, config_loader_with_real_logger, temp_project_base_dir_path):
#     loader = config_loader_with_real_logger
#     with pytest.raises(ConfigError) as excinfo: # Corrected Exception
#         loader.load_specific_project_config(\"non_existent_project\", str(temp_project_base_dir_path))
#     # Corrected Assertion for ConfigError (e.g. file/dir not found)
#     assert \"project directory not found\" in str(excinfo.value).lower() or \\
#            \"failed to load project configuration\" in str(excinfo.value).lower()


# Scenario 2: test_load_project_config_with_invalid_yaml
# @pytest.mark.services
# def test_load_project_config_with_invalid_yaml(self, config_loader_with_real_logger, project_with_invalid_yaml_file):
#     loader = config_loader_with_real_logger
#     with pytest.raises(DXFLibraryNotInstalledError) as excinfo: # Should be ConfigError
#         loader.load_specific_project_config(project_with_invalid_yaml_file[\"project_name\"], project_with_invalid_yaml_file[\"root_dir\"])
#     assert \"ezdxf library not available\" in str(excinfo.value).lower() # Incorrect assertion

# Corrected version:
# @pytest.mark.services
# def test_load_project_config_with_invalid_yaml(self, config_loader_with_real_logger, project_with_invalid_yaml_file):
#     loader = config_loader_with_real_logger
#     with pytest.raises(ConfigError) as excinfo: # Corrected Exception
#         loader.load_specific_project_config(project_with_invalid_yaml_file[\"project_name\"], project_with_invalid_yaml_file[\"root_dir\"])
#     # Corrected Assertion (e.g. YAML parsing error)
#     assert \"error parsing yaml\" in str(excinfo.value).lower() or \\
#            \"validation error\" in str(excinfo.value).lower()

# The following is a placeholder for a more intelligent edit if file contents were available.
# It attempts to provide a broad pattern replacement.

# Replace pytest.raises(DXFLibraryNotInstalledError) with pytest.raises(ConfigError)
# Replace assert "ezdxf library not available" ... with a generic ConfigError message check.

# This edit will use a simplified approach due to the lack of file content:
# It will look for the specific assertion text and change the surrounding context.
# This is risky and might not cover all cases or might introduce errors.

# Given the issues with reading the file, I will attempt a very targeted replacement
# of the most common assertion string if found within a pytest.raises context.
# This is a high-risk edit.

# Attempting a direct, somewhat risky replacement based on the common problematic assertion.
# Find:
# with pytest.raises(DXFLibraryNotInstalledError) as excinfo:
#     ... # some lines of code
# assert "ezdxf library not available" in str(excinfo.value).lower()

# Replace with:
# with pytest.raises(ConfigError) as excinfo: # Changed
#     ... # same lines of code
#     # Changed assertion to be more generic for ConfigError
# assert ("file not found" in str(excinfo.value).lower() or \\
#         "parsing yaml" in str(excinfo.value).lower() or \\
#         "validation error" in str(excinfo.value).lower() or \\
#         "missing 'main' section" in str(excinfo.value).lower() or \\
#         "project directory not found" in str(excinfo.value).lower() or \\
#         "configerror" in str(excinfo.value).lower() or \\ # Added generic ConfigError check
#         "failed to load" in str(excinfo.value).lower())

# Due to tool limitations and inability to reliably see the file,
# I cannot provide a precise diff. The intent is to modify any tests
# that incorrectly expect DXFLibraryNotInstalledError from the ConfigLoaderService
# and instead make them expect ConfigError with appropriate message checks.
# This is a conceptual change.
# For now, no specific code_edit string will be generated to avoid making blind changes.
# I will skip this edit and re-evaluate after the next test run, hoping file access improves.
# If test failures persist in this file and are related to this pattern, PX7 might be needed.
