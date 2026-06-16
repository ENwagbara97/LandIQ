"""
LandIQ — core/units.py
Area Unit Conversion Utilities

Converts computed land area (stored internally in hectares) into
the display formats Nigerians actually use.

Display order (as per UX standard):
    sqm  →  ≈ N plots (State std.)  →  ha

Plot size varies by state. This table reflects the most commonly applied
standard in each state's surveyed layouts and government allocations.
All figures are approximate — actual developer-defined plot sizes vary.
"""

from __future__ import annotations

# ── State-level plot size standards (sqm per plot) ────────────────────────────
# Sources: NIS (Nigerian Institute of Surveyors) guidelines,
# state land use regulations, and widely practised estate layouts.

STATE_PLOT_SQM: dict[str, float] = {
    # South West
    "Lagos":      648.0,   # 60 × 120 ft — dominant in Lagos layouts
    "Ogun":       648.0,   # same standard as Lagos
    "Oyo":        648.0,
    "Osun":       648.0,
    "Ondo":       648.0,
    "Ekiti":      648.0,

    # Federal Capital Territory
    "FCT":        900.0,   # Abuja standard — 30m × 30m
    "Abuja":      900.0,   # alias

    # South South
    "Rivers":     465.0,   # Port Harcourt estate standard — 50 × 100 ft
    "Delta":      648.0,
    "Edo":        648.0,
    "Bayelsa":    465.0,
    "Cross River": 648.0,
    "Akwa Ibom":  648.0,

    # South East
    "Anambra":    465.0,   # 50 × 100 ft common in Onitsha/Awka layouts
    "Enugu":      465.0,
    "Imo":        465.0,
    "Abia":       465.0,
    "Ebonyi":     465.0,

    # North Central
    "Kogi":       648.0,
    "Benue":      648.0,
    "Niger":      648.0,
    "Kwara":      648.0,
    "Nassarawa":  648.0,
    "Plateau":    648.0,

    # North West
    "Kano":       900.0,   # larger plots standard in Kano layouts
    "Kaduna":     648.0,
    "Katsina":    900.0,
    "Sokoto":     900.0,
    "Zamfara":    900.0,
    "Kebbi":      900.0,
    "Jigawa":     900.0,

    # North East
    "Borno":      900.0,
    "Yobe":       900.0,
    "Adamawa":    648.0,
    "Gombe":      648.0,
    "Bauchi":     648.0,
    "Taraba":     648.0,
}

DEFAULT_PLOT_SQM = 648.0   # fallback for unknown / unresolved states


def get_plot_sqm(state: str | None) -> tuple[float, str]:
    """
    Return the standard plot size in sqm for a given state,
    and a label string for display.

    Returns:
        (plot_sqm, label)  e.g.  (648.0, "Lagos")  or  (648.0, "Std.")
    """
    if not state:
        return DEFAULT_PLOT_SQM, "Std."

    # Normalise: strip " State" suffix, strip whitespace, title-case
    key = state.strip().replace(" State", "").title()

    # Direct match
    if key in STATE_PLOT_SQM:
        return STATE_PLOT_SQM[key], key

    # Fuzzy match (handles "Akwa-Ibom" → "Akwa Ibom" etc.)
    key_nospace = key.replace("-", " ").replace("_", " ")
    for k, v in STATE_PLOT_SQM.items():
        if k.lower() == key_nospace.lower():
            return v, k

    return DEFAULT_PLOT_SQM, "Std."


def ha_to_area_display(
    area_ha: float,
    state: str | None = None,
) -> dict:
    """
    Convert a land area in hectares into all Nigerian display formats.

    Display order (standard):
        sqm  →  ≈ N plots (State std.)  →  ha

    Args:
        area_ha: Computed polygon area in hectares.
        state:   Nigerian state name (from reverse geocode) for localised plot size.

    Returns a dict with:
        sqm          : int   — exact square metres
        plots        : float — approximate plot count (1 decimal place)
        plot_sqm_std : float — sqm per plot used for this state
        plot_label   : str   — e.g. "Lagos" or "Std."
        ha           : float — hectares (4 decimal places)

        display_simple : str  — e.g. "4,212 sqm · ≈ 6.3 plots · 0.42 ha"
        display_expert : str  — same format with state label on plots
        display_plots_only : str — e.g. "≈ 6.3 plots"
    """
    sqm = area_ha * 10_000
    plot_sqm, label = get_plot_sqm(state)
    plots = sqm / plot_sqm

    display_simple = (
        f"{sqm:,.0f} sqm  ·  ≈ {plots:.1f} plots  ·  {area_ha:.2f} ha"
    )
    label_text = "(Std.)" if label == "Std." else f"({label} std.)"
    display_expert = (
        f"{sqm:,.0f} sqm  ·  ≈ {plots:.1f} plots {label_text}  ·  {area_ha:.4f} ha"
    )
    display_plots_only = f"≈ {plots:.1f} plots"

    return {
        "sqm":           round(sqm),
        "plots":         round(plots, 1),
        "plot_sqm_std":  plot_sqm,
        "plot_label":    label,
        "ha":            round(area_ha, 4),
        "display_simple": display_simple,
        "display_expert": display_expert,
        "display_plots_only": display_plots_only,
    }
