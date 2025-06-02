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
    def test_plot_shapely_geometry_with_none_geometry(self):
        """Test that plot_shapely_geometry handles None geometry gracefully."""
        result = plot_shapely_geometry(None)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_shapely_geometry_with_empty_geometry(self):
        """Test that plot_shapely_geometry handles empty geometry gracefully."""
        mock_geom = MagicMock()
        mock_geom.is_empty = True
        result = plot_shapely_geometry(mock_geom)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_gdf_with_none_gdf(self):
        """Test that plot_gdf handles None GeoDataFrame gracefully."""
        result = plot_gdf(None)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_gdf_with_empty_gdf(self):
        """Test that plot_gdf handles empty GeoDataFrame gracefully."""
        mock_gdf = MagicMock()
        mock_gdf.empty = True
        result = plot_gdf(mock_gdf)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_shapely_geometry_creates_figure_when_no_ax(self):
        """Test that plot_shapely_geometry creates a figure when no axes provided."""
        import matplotlib.pyplot as plt
        from shapely.geometry import Point

        point = Point(0, 0)

        with patch.object(plt, 'subplots') as mock_subplots, \
             patch.object(plt, 'show') as mock_show:
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_subplots.return_value = (mock_fig, mock_ax)
            plot_shapely_geometry(point)
            mock_subplots.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_gdf_creates_figure_when_no_ax(self):
        """Test that plot_gdf creates a figure when no axes provided."""
        import matplotlib.pyplot as plt
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})

        with patch.object(plt, 'subplots') as mock_subplots, \
             patch.object(plt, 'show') as mock_show, \
             patch.object(gdf, 'plot') as mock_gdf_plot:
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_subplots.return_value = (mock_fig, mock_ax)
            plot_gdf(gdf)
            mock_subplots.assert_called_once()
            mock_gdf_plot.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_functions_accept_kwargs(self):
        """Test that plot functions accept and pass through keyword arguments."""
        mock_geom = MagicMock()
        mock_geom.is_empty = False
        import matplotlib.pyplot as plt
        with patch.object(plt, 'subplots') as mock_subplots:
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_subplots.return_value = (mock_fig, mock_ax)
            plot_shapely_geometry(mock_geom, title="Test Title", color="red", alpha=0.5)
            mock_subplots.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_functions_use_provided_axes(self):
        """Test that plot functions use provided axes instead of creating new ones."""
        mock_geom = MagicMock()
        mock_geom.is_empty = False
        import matplotlib.pyplot as plt
        mock_provided_ax = MagicMock()
        with patch.object(plt, 'subplots') as mock_subplots:
            plot_shapely_geometry(mock_geom, ax=mock_provided_ax)
            mock_subplots.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_point_on_provided_axes(self):
        """Test plotting a Shapely Point on a provided Matplotlib axis."""
        from shapely.geometry import Point
        import matplotlib.pyplot as plt

        test_point = Point(1, 1)
        mock_ax = MagicMock(spec=plt.Axes)
        mock_ax.figure = MagicMock(spec=plt.Figure)

        plot_shapely_geometry(test_point, ax=mock_ax, color='blue', marker='x')

        mock_ax.plot.assert_called_once()
        args, kwargs = mock_ax.plot.call_args
        assert args[0] == [1.0]
        assert args[1] == [1.0]
        assert kwargs.get('color') == 'blue'
        assert kwargs.get('marker') == 'x'

    @pytest.mark.unit
    @pytest.mark.utils
    @pytest.mark.visualization
    @pytest.mark.fast
    def test_plot_gdf_on_provided_axes(self):
        """Test plotting a GeoDataFrame on a provided Matplotlib axis."""
        import geopandas as gpd
        from shapely.geometry import Point
        import matplotlib.pyplot as plt

        test_gdf = gpd.GeoDataFrame({'geometry': [Point(1,1)]}, crs="EPSG:4326")
        mock_ax = MagicMock(spec=plt.Axes)
        mock_ax.figure = MagicMock(spec=plt.Figure)

        with patch.object(test_gdf, 'plot') as mock_gdf_plot_method:
            plot_gdf(test_gdf, ax=mock_ax, color='red')
            mock_gdf_plot_method.assert_called_once_with(ax=mock_ax, color='red')
