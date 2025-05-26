"""Tests for text processing utility functions."""
import pytest

from src.utils.text_processing import sanitize_dxf_layer_name


class TestSanitizeDxfLayerName:
    """Test cases for sanitize_dxf_layer_name function."""

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_valid_layer_names_unchanged(self):
        """Test that valid layer names remain unchanged."""
        valid_names = [
            "Layer1",
            "LAYER_NAME",
            "layer-name",
            "Layer_123",
            "ABC-DEF_123",
            "a",
            "A",
            "1",
            "_",
            "-",
        ]

        for name in valid_names:
            result = sanitize_dxf_layer_name(name)
            assert result == name, f"Valid name '{name}' was changed to '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_spaces_replaced_with_underscores(self):
        """Test that spaces are replaced with underscores."""
        test_cases = [
            ("Layer Name", "Layer_Name"),
            ("My Layer", "My_Layer"),
            ("  Leading Spaces", "__Leading_Spaces"),
            ("Trailing Spaces  ", "Trailing_Spaces__"),
            ("Multiple   Spaces", "Multiple___Spaces"),
            ("Single Space", "Single_Space"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_special_characters_replaced(self):
        """Test that special characters are replaced with underscores."""
        test_cases = [
            ("Layer@Name", "Layer_Name"),
            ("Layer#Name", "Layer_Name"),
            ("Layer%Name", "Layer_Name"),
            ("Layer&Name", "Layer_Name"),
            ("Layer*Name", "Layer_Name"),
            ("Layer+Name", "Layer_Name"),
            ("Layer=Name", "Layer_Name"),
            ("Layer|Name", "Layer_Name"),
            ("Layer\\Name", "Layer_Name"),
            ("Layer/Name", "Layer_Name"),
            ("Layer:Name", "Layer_Name"),
            ("Layer;Name", "Layer_Name"),
            ("Layer<Name", "Layer_Name"),
            ("Layer>Name", "Layer_Name"),
            ("Layer?Name", "Layer_Name"),
            ("Layer[Name]", "Layer_Name_"),
            ("Layer{Name}", "Layer_Name_"),
            ("Layer(Name)", "Layer_Name_"),
            ("Layer\"Name\"", "Layer_Name_"),
            ("Layer'Name'", "Layer_Name_"),
            ("Layer$Name", "Layer_Name"),  # Dollar sign is replaced (implementation is restrictive)
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_unicode_characters_replaced(self):
        """Test that Unicode characters are replaced with underscores."""
        test_cases = [
            ("Layerñame", "Layer_ame"),
            ("Layer名前", "Layer__"),
            ("Layerüber", "Layer_ber"),
            ("Layerçava", "Layer_ava"),
            ("Layer™Name", "Layer_Name"),
            ("Layer©Name", "Layer_Name"),
            ("Layer®Name", "Layer_Name"),
            ("Layer€Name", "Layer_Name"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_mixed_invalid_characters(self):
        """Test combinations of invalid characters."""
        test_cases = [
            ("Layer Name@#$%", "Layer_Name____"),
            ("My-Layer_123!@#", "My-Layer_123___"),
            ("Test/Layer\\Name", "Test_Layer_Name"),
            ("Layer (Copy)", "Layer__Copy_"),
            ("Layer [Modified]", "Layer__Modified_"),
            ("Layer{Version 2}", "Layer_Version_2_"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_empty_and_whitespace_strings(self):
        """Test handling of empty and whitespace-only strings."""
        test_cases = [
            ("", "default_layer"),
            ("   ", "___"),
            ("\t", "_"),
            ("\n", "_"),
            ("\r", "_"),
            ("\t\n\r", "___"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_only_invalid_characters(self):
        """Test strings containing only invalid characters."""
        test_cases = [
            ("@#$%", "____"),
            ("!@#$%^&*()", "__________"),
            ("[]{}()", "______"),
            ("+=|\\/:;", "_______"),
            ("<>?\"'", "_____"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_non_string_input(self):
        """Test handling of non-string input types."""
        test_cases = [
            (123, "123"),
            (123.45, "123_45"),
            (True, "True"),
            (False, "False"),
            (None, "None"),
        ]

        for input_value, expected in test_cases:
            result = sanitize_dxf_layer_name(input_value)
            assert result == expected, f"'{input_value}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_long_layer_names(self):
        """Test handling of very long layer names."""
        # DXF layer names can be quite long, but let's test reasonable lengths
        long_name = "A" * 100
        result = sanitize_dxf_layer_name(long_name)
        assert result == long_name, "Long valid name should remain unchanged"

        long_name_with_spaces = "A" * 50 + " " + "B" * 50
        expected = "A" * 50 + "_" + "B" * 50
        result = sanitize_dxf_layer_name(long_name_with_spaces)
        assert result == expected, "Long name with spaces should have spaces replaced"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_real_world_layer_names(self):
        """Test realistic layer names that might be encountered."""
        test_cases = [
            ("Commercial Buildings", "Commercial_Buildings"),
            ("Residential_Areas", "Residential_Areas"),
            ("Roads & Highways", "Roads___Highways"),
            ("Water Bodies (Lakes)", "Water_Bodies__Lakes_"),
            ("Elevation Contours - 5m", "Elevation_Contours_-_5m"),
            ("Property Lines/Boundaries", "Property_Lines_Boundaries"),
            ("Utilities: Electric", "Utilities__Electric"),
            ("Zoning [Residential]", "Zoning__Residential_"),
            ("Building Footprints v2.1", "Building_Footprints_v2_1"),
            ("Survey Points (GPS)", "Survey_Points__GPS_"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_preserve_case(self):
        """Test that case is preserved in valid characters."""
        test_cases = [
            ("LayerName", "LayerName"),
            ("LAYER_NAME", "LAYER_NAME"),
            ("layer_name", "layer_name"),
            ("MixedCase_Layer", "MixedCase_Layer"),
            ("CamelCaseLayer", "CamelCaseLayer"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"Case should be preserved: '{input_name}' -> '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_consecutive_invalid_characters(self):
        """Test handling of consecutive invalid characters."""
        test_cases = [
            ("Layer@@Name", "Layer__Name"),
            ("Layer###Name", "Layer___Name"),
            ("Layer   Name", "Layer___Name"),
            ("Layer!@#$%Name", "Layer_____Name"),
            ("Layer()[]{}Name", "Layer______Name"),
        ]

        for input_name, expected in test_cases:
            result = sanitize_dxf_layer_name(input_name)
            assert result == expected, f"'{input_name}' should become '{expected}', got '{result}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_edge_cases(self):
        """Test various edge cases."""
        # Test with only underscore (should be preserved)
        assert sanitize_dxf_layer_name("_") == "_"

        # Test with only hyphen (should be preserved)
        assert sanitize_dxf_layer_name("-") == "-"

        # Test combination of valid characters
        assert sanitize_dxf_layer_name("_-") == "_-"

        # Test starting and ending with valid characters
        assert sanitize_dxf_layer_name("_Layer_") == "_Layer_"
        assert sanitize_dxf_layer_name("-Layer-") == "-Layer-"

        # Test dollar sign (gets replaced in current implementation)
        assert sanitize_dxf_layer_name("$Layer$") == "_Layer_"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_idempotency(self):
        """Test that sanitizing an already sanitized name doesn't change it."""
        test_names = [
            "Layer_Name",
            "Valid-Layer",
            "Layer123",
            "UPPERCASE_LAYER",
            "lowercase_layer",
            "Already_Sanitized_Name_123",
        ]

        for name in test_names:
            first_pass = sanitize_dxf_layer_name(name)
            second_pass = sanitize_dxf_layer_name(first_pass)
            assert first_pass == second_pass, f"Sanitization should be idempotent for '{name}'"

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.fast
    def test_performance_with_large_strings(self):
        """Test performance with large strings."""
        import time

        # Create a large string with mixed valid/invalid characters
        large_string = ("Valid_Layer" + "@#$%^&*()" + "More_Valid") * 1000

        start_time = time.time()
        result = sanitize_dxf_layer_name(large_string)
        end_time = time.time()

        # Should complete quickly (under 1 second for this size)
        assert end_time - start_time < 1.0, "Sanitization should be fast even for large strings"

        # Verify the result is correct
        expected = ("Valid_Layer" + "_________" + "More_Valid") * 1000
        assert result == expected, "Large string sanitization should be correct"
