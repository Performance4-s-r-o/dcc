import math

def get_mpe(nominal_value: float, scale_resolution: float) -> float:
    """
    MPE a MPL (hystereze) 
    """
    return math.ceil((0.001 * nominal_value) / scale_resolution) * scale_resolution
