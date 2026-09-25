"""
LandIQ — tests/test_units.py

Tests for core/units.py — Nigerian area unit conversions.
All offline, no external dependencies.
"""
from __future__ import annotations

import pytest
from core.units import get_plot_sqm, ha_to_area_display, DEFAULT_PLOT_SQM


class TestGetPlotSqm:
    def test_lagos_returns_648(self):
        sqm, label = get_plot_sqm("Lagos")
        assert sqm == 648.0
        assert label == "Lagos"

    def test_abuja_returns_900(self):
        sqm, label = get_plot_sqm("FCT")
        assert sqm == 900.0

    def test_abuja_alias_works(self):
        sqm, _ = get_plot_sqm("Abuja")
        assert sqm == 900.0

    def test_rivers_returns_465(self):
        sqm, label = get_plot_sqm("Rivers")
        assert sqm == 465.0

    def test_kano_returns_900(self):
        sqm, _ = get_plot_sqm("Kano")
        assert sqm == 900.0

    def test_strips_state_suffix(self):
        """'Lagos State' should resolve same as 'Lagos'."""
        sqm, label = get_plot_sqm("Lagos State")
        assert sqm == 648.0
        assert label == "Lagos"

    def test_case_insensitive(self):
        sqm, _ = get_plot_sqm("LAGOS")
        assert sqm == 648.0

    def test_none_returns_default(self):
        sqm, label = get_plot_sqm(None)
        assert sqm == DEFAULT_PLOT_SQM
        assert label == "Std."

    def test_unknown_state_returns_default(self):
        sqm, label = get_plot_sqm("Narnia")
        assert sqm == DEFAULT_PLOT_SQM
        assert label == "Std."

    def test_akwa_ibom(self):
        sqm, label = get_plot_sqm("Akwa Ibom")
        assert sqm == 648.0

    def test_cross_river(self):
        sqm, _ = get_plot_sqm("Cross River")
        assert sqm == 648.0


class TestHaToAreaDisplay:
    """Tests for the main display function."""

    def test_basic_conversion_lagos(self):
        result = ha_to_area_display(0.42, state="Lagos")
        assert result["sqm"] == 4200
        # 4200 / 648 ≈ 6.5
        assert result["plots"] == pytest.approx(6.5, abs=0.1)
        assert result["ha"] == 0.42
        assert result["plot_sqm_std"] == 648.0
        assert result["plot_label"] == "Lagos"

    def test_basic_conversion_abuja(self):
        """Abuja standard is 900 sqm/plot."""
        result = ha_to_area_display(0.09, state="FCT")
        # 900 sqm / 900 = 1.0 plot
        assert result["plots"] == pytest.approx(1.0, abs=0.05)

    def test_basic_conversion_rivers(self):
        """Rivers standard is 465 sqm/plot."""
        result = ha_to_area_display(0.0465, state="Rivers")
        assert result["plots"] == pytest.approx(1.0, abs=0.05)

    def test_sqm_is_exact(self):
        result = ha_to_area_display(1.0)
        assert result["sqm"] == 10_000

    def test_display_simple_contains_all_units(self):
        result = ha_to_area_display(0.42, state="Lagos")
        s = result["display_simple"]
        assert "sqm" in s
        assert "plots" in s
        assert "ha" in s

    def test_display_expert_contains_state_label(self):
        result = ha_to_area_display(0.42, state="Lagos")
        s = result["display_expert"]
        assert "Lagos std." in s

    def test_display_expert_std_label_for_unknown_state(self):
        result = ha_to_area_display(0.42, state=None)
        assert "Std." in result["display_expert"]

    def test_display_plots_only(self):
        result = ha_to_area_display(0.42, state="Lagos")
        assert result["display_plots_only"].startswith("≈")
        assert "plots" in result["display_plots_only"]

    def test_sqm_before_plots_before_ha_in_display(self):
        """Verify the display order: sqm first, then plots, then ha."""
        result = ha_to_area_display(0.42, state="Lagos")
        s = result["display_simple"]
        idx_sqm   = s.index("sqm")
        idx_plots = s.index("plots")
        idx_ha    = s.index("ha")
        assert idx_sqm < idx_plots < idx_ha, (
            f"Expected sqm < plots < ha but got: {s}"
        )

    def test_large_parcel(self):
        """5 hectares in Lagos = ~77 plots."""
        result = ha_to_area_display(5.0, state="Lagos")
        assert result["sqm"] == 50_000
        assert result["plots"] == pytest.approx(77.2, abs=0.2)

    def test_tiny_parcel(self):
        """Very small parcel — 50 sqm — should still work."""
        result = ha_to_area_display(0.005, state="Lagos")
        assert result["sqm"] == 50
        assert result["plots"] < 1.0

    def test_ha_rounded_to_4dp_in_expert(self):
        result = ha_to_area_display(0.123456789, state="Lagos")
        assert "0.1235" in result["display_expert"]
