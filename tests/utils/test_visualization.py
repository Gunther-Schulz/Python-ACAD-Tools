"""Tests for visualization utility functions."""
import pytest
from unittest.mock import patch, MagicMock

from src.utils.visualization import plot_shapely_geometry, plot_gdf


class TestVisualizationUtilities:
    """Test cases for visualization utility functions."""

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_shapely_geometry_without_dependencies(self):
        """Test that plot_shapely_geometry handles missing dependencies gracefully."""
        # Mock the availability flags to simulate missing dependencies
        with patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', False), \
             patch('src.utils.visualization._SHAPELY_AVAILABLE', False):

            # This should not raise an error, just return early
            result = plot_shapely_geometry(None)
            assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_gdf_without_dependencies(self):
        """Test that plot_gdf handles missing dependencies gracefully."""
        # Mock the availability flags to simulate missing dependencies
        with patch('src.utils.visualization._GEOPANDAS_AVAILABLE', False), \
             patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', False):

            # This should not raise an error, just return early
            result = plot_gdf(None)
            assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_shapely_geometry_with_none_geometry(self):
        """Test that plot_shapely_geometry handles None geometry gracefully."""
        # Even with dependencies available, None geometry should return early
        with patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', True), \
             patch('src.utils.visualization._SHAPELY_AVAILABLE', True):

            result = plot_shapely_geometry(None)
            assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_shapely_geometry_with_empty_geometry(self):
        """Test that plot_shapely_geometry handles empty geometry gracefully."""
        # Mock an empty geometry
        mock_geom = MagicMock()
        mock_geom.is_empty = True

        with patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', True), \
             patch('src.utils.visualization._SHAPELY_AVAILABLE', True):

            result = plot_shapely_geometry(mock_geom)
            assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_gdf_with_none_gdf(self):
        """Test that plot_gdf handles None GeoDataFrame gracefully."""
        with patch('src.utils.visualization._GEOPANDAS_AVAILABLE', True), \
             patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', True):

            result = plot_gdf(None)
            assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_gdf_with_empty_gdf(self):
        """Test that plot_gdf handles empty GeoDataFrame gracefully."""
        # Mock an empty GeoDataFrame
        mock_gdf = MagicMock()
        mock_gdf.empty = True

        with patch('src.utils.visualization._GEOPANDAS_AVAILABLE', True), \
             patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', True):

            result = plot_gdf(mock_gdf)
            assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    @pytest.mark.skipif("not hasattr(__import__('src.utils.visualization'), '_MATPLOTLIB_AVAILABLE') or not __import__('src.utils.visualization')._MATPLOTLIB_AVAILABLE")
    def test_plot_shapely_geometry_creates_figure_when_no_ax(self):
        """Test that plot_shapely_geometry creates a figure when no axes provided."""
        # This test only runs if matplotlib is actually available
        try:
            import matplotlib.pyplot as plt
            from shapely.geometry import Point

            # Create a simple point geometry
            point = Point(0, 0)

            with patch.object(plt, 'subplots') as mock_subplots, \
                 patch.object(plt, 'show') as mock_show:

                mock_fig = MagicMock()
                mock_ax = MagicMock()
                mock_subplots.return_value = (mock_fig, mock_ax)

                # Call the function
                plot_shapely_geometry(point)

                # Verify that subplots was called (figure was created)
                mock_subplots.assert_called_once()

        except ImportError:
            pytest.skip("matplotlib or shapely not available")

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    @pytest.mark.skipif("not hasattr(__import__('src.utils.visualization'), '_GEOPANDAS_AVAILABLE') or not __import__('src.utils.visualization')._GEOPANDAS_AVAILABLE")
    def test_plot_gdf_creates_figure_when_no_ax(self):
        """Test that plot_gdf creates a figure when no axes provided."""
        # This test only runs if geopandas and matplotlib are actually available
        try:
            import matplotlib.pyplot as plt
            import geopandas as gpd
            from shapely.geometry import Point

            # Create a simple GeoDataFrame
            gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})

            with patch.object(plt, 'subplots') as mock_subplots, \
                 patch.object(plt, 'show') as mock_show, \
                 patch.object(gdf, 'plot') as mock_plot:

                mock_fig = MagicMock()
                mock_ax = MagicMock()
                mock_subplots.return_value = (mock_fig, mock_ax)

                # Call the function
                plot_gdf(gdf)

                # Verify that subplots was called (figure was created)
                mock_subplots.assert_called_once()
                # Verify that gdf.plot was called
                mock_plot.assert_called_once()

        except ImportError:
            pytest.skip("geopandas, matplotlib, or shapely not available")

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_functions_accept_kwargs(self):
        """Test that plot functions accept and pass through keyword arguments."""
        # Mock dependencies
        with patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', True), \
             patch('src.utils.visualization._SHAPELY_AVAILABLE', True):

            # Mock geometry
            mock_geom = MagicMock()
            mock_geom.is_empty = False

            # Mock matplotlib components
            with patch('matplotlib.pyplot.subplots') as mock_subplots:
                mock_fig = MagicMock()
                mock_ax = MagicMock()
                mock_subplots.return_value = (mock_fig, mock_ax)

                # Call with kwargs - should not raise an error
                plot_shapely_geometry(mock_geom, title="Test Title", color="red", alpha=0.5)

                # Verify subplots was called
                mock_subplots.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_functions_use_provided_axes(self):
        """Test that plot functions use provided axes instead of creating new ones."""
        # Mock dependencies
        with patch('src.utils.visualization._MATPLOTLIB_AVAILABLE', True), \
             patch('src.utils.visualization._SHAPELY_AVAILABLE', True):

            # Mock geometry
            mock_geom = MagicMock()
            mock_geom.is_empty = False

            # Mock provided axes
            mock_ax = MagicMock()
            mock_fig = MagicMock()
            mock_ax.figure = mock_fig

            # Mock matplotlib components
            with patch('matplotlib.pyplot.subplots') as mock_subplots, \
                 patch('matplotlib.pyplot.show') as mock_show:

                # Call with provided axes
                plot_shapely_geometry(mock_geom, ax=mock_ax)

                # Verify subplots was NOT called (we provided axes)
                mock_subplots.assert_not_called()
                # Verify show was NOT called (we provided axes)
                mock_show.assert_not_called()
