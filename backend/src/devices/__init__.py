"""
Device Management - Muse headband discovery, connection, and monitoring
"""
from .manager import DeviceManager
from .stream import LSLStreamHandler

__all__ = ['DeviceManager', 'LSLStreamHandler']
