"""
Signal Processing - Multi-timescale EEG analysis and neurofeedback computation
"""
from .multi_scale import MultiScaleProcessor
from .rate_control import RateController, ui_broadcast_loop
from . import utils

__all__ = ['MultiScaleProcessor', 'RateController', 'ui_broadcast_loop', 'utils']
