"""Read-only validation shared by preparation and the local dashboard."""

import math


def result_is_usable(result):
    """Reject explicitly invalid results and legacy constant fill-value spectra."""
    if not isinstance(result, dict):
        return False
    quality = result.get('data_quality') or {}
    if not isinstance(quality, dict) or quality.get('status') == 'invalid':
        return False
    powers = result.get('P', [])
    if not powers:
        return False
    try:
        if not all(math.isfinite(float(value)) for value in powers):
            return False
        vertical = result.get('nZ', [])
        horizontal = result.get('nG', [])
        # Old outputs retained 99999 in all three components. Do not call
        # their identical P=0.5, constant-power spectra valid observations.
        if len(vertical) == len(horizontal) == len(powers):
            constant = all(math.isclose(float(value), float(vertical[0]),
                                        rel_tol=1e-12) for value in vertical)
            fill_ratio = all(math.isclose(float(value), 0.5, abs_tol=1e-12,
                                          rel_tol=0) for value in powers)
            double_power = all(math.isclose(float(g), 2 * float(z), rel_tol=1e-12)
                               for z, g in zip(vertical, horizontal))
            if constant and fill_ratio and double_power:
                return False
    except (TypeError, ValueError, IndexError):
        return False
    return True
