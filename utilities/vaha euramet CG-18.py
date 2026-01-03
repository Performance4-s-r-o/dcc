import math

def get_mpe(nominal_value: float, scale_resolution: float) -> tuple[float, float]:
    """
    MPE 
    """
    mpe = math.ceil((0.001 * nominal_value) / scale_resolution) * scale_resolution
    return mpe

def get_mpl(k_up: float, k_down: float) -> float:
    """
    MPL (hystereze) 
    """
    return abs(k_up - k_down)

def mpl_evaluation(nominal_value: float, scale_resolution: float, k_up: float, k_down: float) -> float:
    """
    MPL evaluation
    :param nominal_value: Nominal value for MPE calculation.
    :param scale_resolution: Scale resolution for MPE calculation.
    :param k_up: Upward measurement value.
    :param k_down: Downward measurement value.

    Returns True if MPL is within MPE
    """
    if get_mpe(nominal_value, scale_resolution) >= get_mpl(k_up, k_down):
        return True 
    else:
        return False

def mpe_evaluation(nominal_value: float, scale_resolution: float, k_up: float, k_down: float, uBE: float) -> float:
    """
    MPE evaluation
    :param nominal_value: Nominal value for MPE calculation.
    :param scale_resolution: Scale resolution for MPE calculation.
    :param k_up: Upward measurement value.
    :param k_down: Downward measurement value.
    :param uBE: Uncertainty of etalon.

    Returns True if MPE is within MPE
    """
    k = (k_up + k_down) / 2
    BI = k - nominal_value
    if abs(BI) + uBE <= get_mpe(nominal_value, scale_resolution):
        return True
    else:
        return False
