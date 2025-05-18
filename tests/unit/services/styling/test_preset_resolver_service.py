import unittest
from unittest.mock import MagicMock, patch
import logging

from dxfplanner.config.schemas import ProjectConfig, StyleObjectConfig, LayerDisplayPropertiesConfig, TextStylePropertiesConfig, ColorModel
from dxfplanner.services.styling.preset_resolver_service import PresetResolverService

class TestPresetResolverService(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock(spec=logging.Logger)
        self.mock_project_config = MagicMock(spec=ProjectConfig)

        self.preset1_config = StyleObjectConfig(
            layer_props=LayerDisplayPropertiesConfig(color=ColorModel(aci=1)),
            text_props=TextStylePropertiesConfig(font_name_or_style_preset="Arial_from_preset")
        )
        self.mock_project_config.style_presets = {
            "preset1_exists": self.preset1_config
        }
        self.service = PresetResolverService(project_config=self.mock_project_config, logger=self.mock_logger)

    def test_resolve_only_preset_found(self):
        result = self.service.resolve_preset_and_inline("preset1_exists", None, "TestContext1")
        self.assertIsNotNone(result.layer_props)
        self.assertIsNotNone(result.layer_props.color)
        self.assertEqual(result.layer_props.color.aci, 1)
        self.assertIsNotNone(result.text_props)
        self.assertEqual(result.text_props.font_name_or_style_preset, "Arial_from_preset")

    def test_resolve_preset_not_found_no_inline(self):
        result = self.service.resolve_preset_and_inline("preset_not_exists", None, "TestContext2")
        self.assertIsInstance(result, StyleObjectConfig)
        self.assertIsNotNone(result.layer_props)
        self.assertIsNone(result.layer_props.color)
        self.mock_logger.warning.assert_called_with("PresetResolver for 'TestContext2': Style preset 'preset_not_exists' not found.")

    def test_resolve_only_inline_no_preset_name(self):
        inline_style = StyleObjectConfig(
            layer_props=LayerDisplayPropertiesConfig(color=ColorModel(aci=2))
        )
        result = self.service.resolve_preset_and_inline(None, inline_style, "TestContext3")
        self.assertIsNotNone(result.layer_props)
        self.assertIsNotNone(result.layer_props.color)
        self.assertEqual(result.layer_props.color.aci, 2)

    def test_resolve_preset_found_and_inline_provided_inline_overrides(self):
        inline_style = StyleObjectConfig(
            layer_props=LayerDisplayPropertiesConfig(color=ColorModel(aci=3)),
            text_props=TextStylePropertiesConfig(font_name_or_style_preset="Times_from_inline")
        )
        result = self.service.resolve_preset_and_inline("preset1_exists", inline_style, "TestContext4")
        self.assertIsNotNone(result.layer_props)
        self.assertIsNotNone(result.layer_props.color)
        self.assertEqual(result.layer_props.color.aci, 3)
        self.assertIsNotNone(result.text_props)
        self.assertEqual(result.text_props.font_name_or_style_preset, "Times_from_inline")

    def test_resolve_preset_not_found_but_inline_provided(self):
        inline_style = StyleObjectConfig(
            layer_props=LayerDisplayPropertiesConfig(color=ColorModel(aci=4))
        )
        result = self.service.resolve_preset_and_inline("preset_not_exists_again", inline_style, "TestContext5")
        self.assertIsNotNone(result.layer_props)
        self.assertIsNotNone(result.layer_props.color)
        self.assertEqual(result.layer_props.color.aci, 4)
        self.mock_logger.warning.assert_called_with("PresetResolver for 'TestContext5': Style preset 'preset_not_exists_again' not found.")

    def test_resolve_no_preset_name_no_inline(self):
        result = self.service.resolve_preset_and_inline(None, None, "TestContext6")
        self.assertIsInstance(result, StyleObjectConfig)
        self.assertIsNotNone(result.layer_props)
        self.assertIsNone(result.layer_props.color)

    def test_resolve_preset_has_some_none_inline_fills_them(self):
        preset_partial_config = StyleObjectConfig(
             text_props=TextStylePropertiesConfig(font_name_or_style_preset="Partial_Preset_Font")
        )
        self.mock_project_config.style_presets["partial_preset"] = preset_partial_config

        inline_fill = StyleObjectConfig(
            layer_props=LayerDisplayPropertiesConfig(color=ColorModel(aci=5))
        )

        result = self.service.resolve_preset_and_inline("partial_preset", inline_fill, "TestContext7")
        self.assertIsNotNone(result.text_props)
        self.assertEqual(result.text_props.font_name_or_style_preset, "Partial_Preset_Font")
        self.assertIsNotNone(result.layer_props)
        self.assertIsNotNone(result.layer_props.color)
        self.assertEqual(result.layer_props.color.aci, 5)

if __name__ == '__main__':
    unittest.main()
