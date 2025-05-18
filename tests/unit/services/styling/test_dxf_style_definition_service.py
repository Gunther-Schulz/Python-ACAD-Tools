import unittest
from unittest.mock import MagicMock, call, patch
import logging
import ezdxf

from dxfplanner.config.style_schemas import TextStylePropertiesConfig
from dxfplanner.services.styling.dxf_style_definition_service import DxfStyleDefinitionService

class TestDxfStyleDefinitionService(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock(spec=logging.Logger)
        self.service = DxfStyleDefinitionService(logger=self.mock_logger)
        # self.doc = ezdxf.new() # Tests will create their own fresh docs for isolation

    def tearDown(self):
        pass

    def test_ensure_text_style_new_style_created(self):
        style_name = "TestStyle1"
        text_props = TextStylePropertiesConfig(
            resolved_font_filename="arial.ttf",
            height=0.25, # Note: service currently forces height = 0.0 in STYLE
            width_factor=0.8,
            oblique_angle=15.0
        )
        doc = ezdxf.new() # Fresh doc for this test

        self.service.ensure_text_style_in_dxf(doc, style_name, text_props)

        self.assertTrue(doc.styles.has_entry(style_name))
        created_style = doc.styles.get(style_name)
        self.assertEqual(created_style.dxf.font, "arial.ttf")
        self.assertEqual(created_style.dxf.height, 0.0) # As per current service logic
        self.assertEqual(created_style.dxf.width, 0.8)
        self.assertEqual(created_style.dxf.oblique, 15.0)
        self.mock_logger.info.assert_any_call(f"DXF STYLE '{style_name}': Creating new entry using font 'arial.ttf'.")
        self.mock_logger.info.assert_any_call(f"DXF STYLE '{style_name}': Successfully created with attributes: {{'font': 'arial.ttf', 'height': 0.0, 'width': 0.8, 'oblique': 15.0}}")

    def test_ensure_text_style_no_resolved_font(self):
        style_name = "TestStyle_NoFont"
        text_props = TextStylePropertiesConfig(font_name_or_style_preset="SomePresetName") # resolved_font_filename is None
        doc = ezdxf.new()

        self.service.ensure_text_style_in_dxf(doc, style_name, text_props)

        self.assertFalse(doc.styles.has_entry(style_name))
        self.mock_logger.warning.assert_called_with(
            f"DXF STYLE '{style_name}': Cannot create. No font file was resolved in text_props. "
            f"Input text_props.font_name_or_style_preset was 'SomePresetName'."
        )

    def test_ensure_text_style_already_exists_same_font(self):
        style_name = "ExistingStyleSameFont"
        font_file = "comic.ttf"
        doc = ezdxf.new()
        doc.styles.new(style_name, dxfattribs={"font": font_file, "height": 0.0})

        text_props = TextStylePropertiesConfig(resolved_font_filename=font_file)

        self.service.ensure_text_style_in_dxf(doc, style_name, text_props)

        self.mock_logger.debug.assert_called_with(
            f"DXF STYLE '{style_name}': Already exists in DXF with the same font '{font_file}'. Skipping creation."
        )
        # Verify no new attempt to create by checking specific info logs
        # Collect all info log messages
        info_logs = [c[0][0] for c in self.mock_logger.info.call_args_list]
        self.assertFalse(any(f"DXF STYLE '{style_name}': Creating new entry" in log for log in info_logs))


    def test_ensure_text_style_already_exists_different_font(self):
        style_name = "ExistingStyleDiffFont"
        existing_font = "times.ttf"
        new_font = "arial.ttf"
        doc = ezdxf.new()
        doc.styles.new(style_name, dxfattribs={"font": existing_font, "height": 0.0})

        text_props = TextStylePropertiesConfig(resolved_font_filename=new_font)

        self.service.ensure_text_style_in_dxf(doc, style_name, text_props)

        self.mock_logger.warning.assert_called_with(
            f"DXF STYLE '{style_name}': Already exists in DXF but with a DIFFERENT font "
            f"('{existing_font}' vs desired '{new_font}'). "
            f"The existing style will NOT be overwritten."
        )
        info_logs = [c[0][0] for c in self.mock_logger.info.call_args_list]
        self.assertFalse(any(f"DXF STYLE '{style_name}': Creating new entry" in log for log in info_logs))


    def test_ensure_text_style_minimal_props(self):
        style_name = "TestStyleMinimal"
        text_props = TextStylePropertiesConfig(resolved_font_filename="minifont.shx")
        doc = ezdxf.new()

        self.service.ensure_text_style_in_dxf(doc, style_name, text_props)

        self.assertTrue(doc.styles.has_entry(style_name))
        created_style = doc.styles.get(style_name)
        self.assertEqual(created_style.dxf.font, "minifont.shx")
        self.assertEqual(created_style.dxf.height, 0.0)
        self.assertEqual(created_style.dxf.width, 1.0)
        self.assertEqual(created_style.dxf.oblique, 0.0)
        self.mock_logger.info.assert_any_call(f"DXF STYLE '{style_name}': Creating new entry using font 'minifont.shx'.")

        # Construct the expected message to avoid f-string parsing issues with {{...}}
        expected_msg_part1 = f"DXF STYLE '{style_name}': Successfully created with attributes: "
        expected_msg_part2 = "{'font': 'minifont.shx', 'height': 0.0}"
        expected_final_message = expected_msg_part1 + expected_msg_part2
        self.mock_logger.info.assert_any_call(expected_final_message)

    def test_ensure_text_style_creation_failure_ezdxf_error(self):
        style_name = "TestStyleFail"
        text_props = TextStylePropertiesConfig(resolved_font_filename="goodfont.ttf")
        doc = ezdxf.new()

        # Mock doc.styles.new to raise an error
        with patch.object(doc.styles, 'new', side_effect=ezdxf.DXFError("Test DXFError from mock")) as mock_new_method:
            self.service.ensure_text_style_in_dxf(doc, style_name, text_props)

        mock_new_method.assert_called_once()

        # Construct the expected message without complex f-string for the dict part
        expected_message_part1 = f"DXF STYLE '{style_name}': Failed to create STYLE entry in DXF. Error: Test DXFError from mock. "
        expected_message_part2 = "Attributes: {'font': 'goodfont.ttf', 'height': 0.0}"
        expected_log_message = expected_message_part1 + expected_message_part2

        self.mock_logger.error.assert_called_with(expected_log_message)

if __name__ == '__main__':
    unittest.main()
