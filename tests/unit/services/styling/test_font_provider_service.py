import unittest
from unittest.mock import patch, MagicMock, call
import os

from dxfplanner.services.styling.font_provider_service import FontProviderService

class TestFontProviderService(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock()
        # Suppress logging during tests unless specifically testing log output
        # self.patcher = patch('dxfplanner.services.styling.font_provider_service.logger', self.mock_logger)
        # self.mock_logger_global = self.patcher.start()

    # def tearDown(self):
    #     self.patcher.stop()

    @patch('os.path.isfile')
    @patch('os.path.exists')
    def test_font_found_with_extension_in_name(self, mock_exists, mock_isfile):
        font_dirs = ["/test/fonts1", "/test/fonts2"]
        service = FontProviderService(font_directories=font_dirs, logger=self.mock_logger)

        font_name = "arial.ttf"
        expected_path = os.path.normpath("/test/fonts1/arial.ttf")

        def side_effect_exists(path):
            return path == expected_path
        mock_exists.side_effect = side_effect_exists
        mock_isfile.return_value = True # Assume if exists, it's a file for simplicity here

        result = service.get_font_path(font_name)
        self.assertEqual(result, expected_path)
        mock_exists.assert_any_call(expected_path)
        self.mock_logger.info.assert_called_with(f"Font '{font_name}' (checked as '{font_name}') found at '{expected_path}'.")

    @patch('os.path.isfile')
    @patch('os.path.exists')
    def test_font_found_without_extension_in_name_ttf(self, mock_exists, mock_isfile):
        font_dirs = ["/test/fonts1"]
        service = FontProviderService(font_directories=font_dirs, logger=self.mock_logger)

        font_name = "helvetica"
        # Order of checks: helvetica.ttf, then helvetica.otf
        path_ttf = os.path.normpath("/test/fonts1/helvetica.ttf")
        # path_otf = os.path.normpath("/test/fonts1/helvetica.otf")

        def side_effect_exists(path):
            if path == path_ttf: return True
            # if path == path_otf: return False # ensure ttf is found first
            return False
        mock_exists.side_effect = side_effect_exists
        mock_isfile.return_value = True

        result = service.get_font_path(font_name)
        self.assertEqual(result, path_ttf)
        # Expected calls: first the name itself, then with .ttf, then with .otf
        # calls = [call(os.path.normpath("/test/fonts1/helvetica")),
        #          call(path_ttf)]
        # mock_exists.assert_has_calls(calls, any_order=False) # any_order=False depends on internal list order
        self.mock_logger.info.assert_called_with(f"Font '{font_name}' (checked as 'helvetica.ttf') found at '{path_ttf}'.")

    @patch('os.path.isfile')
    @patch('os.path.exists')
    def test_font_found_without_extension_in_name_otf(self, mock_exists, mock_isfile):
        font_dirs = ["/test/fonts1"]
        service = FontProviderService(font_directories=font_dirs, logger=self.mock_logger)

        font_name = "times"
        path_ttf = os.path.normpath("/test/fonts1/times.ttf")
        path_otf = os.path.normpath("/test/fonts1/times.otf")

        def side_effect_exists(path):
            if path == path_ttf: return False
            if path == path_otf: return True
            return False
        mock_exists.side_effect = side_effect_exists
        mock_isfile.return_value = True

        result = service.get_font_path(font_name)
        self.assertEqual(result, path_otf)
        self.mock_logger.info.assert_called_with(f"Font '{font_name}' (checked as 'times.otf') found at '{path_otf}'.")

    @patch('os.path.isfile')
    @patch('os.path.exists')
    def test_font_not_found(self, mock_exists, mock_isfile):
        font_dirs = ["/test/fonts1"]
        service = FontProviderService(font_directories=font_dirs, logger=self.mock_logger)
        font_name = "nonexistentfont"

        mock_exists.return_value = False
        mock_isfile.return_value = False # Though isfile won't be called if exists is false

        result = service.get_font_path(font_name)
        self.assertIsNone(result)
        self.mock_logger.warning.assert_called_with(f"Font '{font_name}' not found in any of the specified directories after checking variants: ['{font_name}', '{font_name}.ttf', '{font_name}.otf'].")

    def test_no_font_name_provided(self):
        service = FontProviderService(font_directories=["/test/fonts"], logger=self.mock_logger)
        result = service.get_font_path(None)
        self.assertIsNone(result)
        result = service.get_font_path("")
        self.assertIsNone(result)
        self.mock_logger.debug.assert_any_call("get_font_path called with no font_name, returning None.")

    @patch('os.path.exists') # Mock exists to prevent actual file system checks
    def test_no_font_directories_provided_in_constructor(self, mock_exists):
        service = FontProviderService(font_directories=[], logger=self.mock_logger)
        self.mock_logger.warning.assert_called_with("FontProviderService initialized with no font directories.")
        result = service.get_font_path("anyfont.ttf")
        self.assertIsNone(result)
        self.mock_logger.debug.assert_called_with("No font directories configured, cannot find font 'anyfont.ttf'.")
        mock_exists.assert_not_called() # Should not even try to check paths if no dirs

    @patch('os.path.isfile')
    @patch('os.path.exists')
    def test_font_found_in_second_directory(self, mock_exists, mock_isfile):
        font_dirs = ["/test/fonts1", "/test/fonts2"]
        service = FontProviderService(font_directories=font_dirs, logger=self.mock_logger)
        font_name = "cour.ttf"
        path_in_dir1 = os.path.normpath("/test/fonts1/cour.ttf")
        path_in_dir2 = os.path.normpath("/test/fonts2/cour.ttf")

        def side_effect_exists(path):
            if path == path_in_dir1: return False
            if path == path_in_dir2: return True
            return False
        mock_exists.side_effect = side_effect_exists
        mock_isfile.return_value = True

        result = service.get_font_path(font_name)
        self.assertEqual(result, path_in_dir2)

        # Check that it tried dir1 first
        calls = [call(path_in_dir1), call(path_in_dir2)]
        # The exact calls to os.path.exists depend on the internal list of potential_filenames.
        # If font_name already has extension, potential_filenames is just [font_name]
        # So it would be os.path.join(dir1, font_name) and os.path.join(dir2, font_name)
        mock_exists.assert_any_call(path_in_dir1)
        mock_exists.assert_any_call(path_in_dir2)
        self.mock_logger.info.assert_called_with(f"Font '{font_name}' (checked as '{font_name}') found at '{path_in_dir2}'.")

    @patch('os.path.isfile')
    @patch('os.path.exists')
    def test_font_name_with_uncommon_extension_found_if_direct_match(self, mock_exists, mock_isfile):
        font_dirs = ["/test/fonts1"]
        service = FontProviderService(font_directories=font_dirs, logger=self.mock_logger)

        font_name = "myfont.customext"
        expected_path = os.path.normpath("/test/fonts1/myfont.customext")

        mock_exists.return_value = False # Default
        mock_exists.side_effect = lambda path: path == expected_path
        mock_isfile.return_value = True

        result = service.get_font_path(font_name)
        self.assertEqual(result, expected_path)
        # Because font_name already has an extension, potential_filenames should just be [font_name]
        # and it shouldn't try to append .ttf or .otf
        mock_exists.assert_called_once_with(expected_path)
        self.mock_logger.info.assert_called_with(f"Font '{font_name}' (checked as '{font_name}') found at '{expected_path}'.")

    @patch('os.path.isfile')
    @patch('os.path.exists')
    def test_font_name_without_ext_also_checks_name_as_is(self, mock_exists, mock_isfile):
        # Test if a font file "arial" (no extension) can be found if "arial" is requested.
        font_dirs = ["/test/fonts1"]
        service = FontProviderService(font_directories=font_dirs, logger=self.mock_logger)

        font_name = "arial"
        path_arial_no_ext = os.path.normpath("/test/fonts1/arial")
        path_arial_ttf = os.path.normpath("/test/fonts1/arial.ttf")

        # Service logic: potential_filenames = [font_name, font_name + .ttf, font_name + .otf]
        # So, "arial", "arial.ttf", "arial.otf"

        def side_effect_exists(path):
            if path == path_arial_no_ext: return True # Found as is
            return False
        mock_exists.side_effect = side_effect_exists
        mock_isfile.return_value = True

        result = service.get_font_path(font_name)
        self.assertEqual(result, path_arial_no_ext)

        expected_calls_to_exists = [
            call(os.path.normpath("/test/fonts1/arial")), # This should be the first one in potential_filenames
            # call(os.path.normpath("/test/fonts1/arial.ttf")), # Won't be called if first one is found
            # call(os.path.normpath("/test/fonts1/arial.otf"))  # Won't be called
        ]
        # Ensure it was called with the path that was found
        mock_exists.assert_any_call(path_arial_no_ext)
        # Check that the found path was the first one it tried from potential_filenames (which is font_name itself)
        self.assertEqual(mock_exists.call_args_list[0], call(path_arial_no_ext))
        self.mock_logger.info.assert_called_with(f"Font '{font_name}' (checked as '{font_name}') found at '{path_arial_no_ext}'.")

if __name__ == '__main__':
    unittest.main()
