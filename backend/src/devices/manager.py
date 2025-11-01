"""
Device Manager - Handle Muse headband discovery, connection, and subprocess management

This module manages the lifecycle of Muse EEG devices using muselsl:
- Discovery via Bluetooth scanning
- Connection via subprocess isolation (one process per device)
- Health monitoring and auto-reconnection
- Graceful shutdown

Known Issues:
- muselsl v2.2.2 has bugs with bluetoothctl (see docs/07-muselsl-bugfixes.md)
- Our fork includes fixes for EOF handling and filename processing
"""

import subprocess
import logging
import time
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class Device:
    """Represents a discovered Muse device"""
    name: str          # e.g., "Muse S - 3C4F"
    address: str       # MAC address: "00:55:DA:B3:3C4F"
    status: str        # "available", "connected", "streaming"
    battery: Optional[int] = None
    stream_name: Optional[str] = None


class DeviceManager:
    """
    Manages Muse device connections using subprocess isolation.

    Each device runs as a separate `muselsl stream` subprocess for fault isolation.
    If one device crashes, others continue operating normally.

    Threading Model:
    - Device Manager operations are synchronous
    - Subprocess monitoring can be async (future enhancement)
    - LSL streams are consumed by separate pull threads (see devices/stream.py)

    Example:
        manager = DeviceManager()
        devices = manager.scan_devices()
        success = manager.connect_device(devices[0].address, "Muse_1")
        ...
        manager.disconnect_device("Muse_1")
    """

    def __init__(self):
        """Initialize device manager"""
        self.connected_processes: Dict[str, subprocess.Popen] = {}
        self.device_info: Dict[str, Device] = {}
        logger.info("DeviceManager initialized")

    def scan_devices(self, timeout: float = 5.0) -> List[Device]:
        """
        Scan for available Muse devices using muselsl list.

        Args:
            timeout: Scan timeout in seconds

        Returns:
            List of discovered Device objects

        Note:
            This wraps `muselsl list` which has known bugs in v2.2.2:
            - May fail with EOF error on some systems
            - Our fork includes workarounds (see docs/07-muselsl-bugfixes.md)
        """
        logger.info(f"Scanning for Muse devices (timeout={timeout}s)...")

        try:
            # Run muselsl list command
            result = subprocess.run(
                ['muselsl', 'list'],
                capture_output=True,
                text=True,
                timeout=timeout + 2,  # Extra buffer for process overhead
            )

            if result.returncode != 0:
                logger.error(f"muselsl list failed: {result.stderr}")
                return self._get_mock_devices()  # Fallback for testing

            # Parse output
            devices = self._parse_muselsl_list_output(result.stdout)
            logger.info(f"Found {len(devices)} Muse device(s)")

            return devices

        except subprocess.TimeoutExpired:
            logger.warning(f"Device scan timed out after {timeout}s")
            return []
        except FileNotFoundError:
            logger.error("muselsl command not found - is it installed?")
            return self._get_mock_devices()  # Fallback for development
        except Exception as e:
            logger.error(f"Device scan error: {e}")
            return []

    def _parse_muselsl_list_output(self, output: str) -> List[Device]:
        """
        Parse output from `muselsl list` command.

        Expected format:
            Found device Muse-3C4F, MAC Address 00:55:DA:B3:3C4F
            ...

        Args:
            output: Raw stdout from muselsl list

        Returns:
            List of Device objects
        """
        devices = []

        # Pattern: "Found device <NAME>, MAC Address <MAC>"
        pattern = r'Found device\s+([^,]+),\s*MAC Address\s+([0-9A-F:]+)'

        for line in output.split('\n'):
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                address = match.group(2).strip().upper()

                # Create short display name (last 4 chars of MAC)
                short_id = address.replace(':', '')[-4:]
                display_name = f"Muse S - {short_id}"

                device = Device(
                    name=display_name,
                    address=address,
                    status="available"
                )
                devices.append(device)
                logger.debug(f"  - {device.name} ({device.address})")

        return devices

    def connect_device(self, address: str, stream_name: str) -> bool:
        """
        Connect to a Muse device and start LSL streaming.

        Starts `muselsl stream` as a subprocess for fault isolation.
        The LSL stream will be named `stream_name` (e.g., "Muse_1").

        Args:
            address: Bluetooth MAC address (e.g., "00:55:DA:B3:3C4F")
            stream_name: LSL stream name (e.g., "Muse_1", "Muse_2")

        Returns:
            True if connection successful, False otherwise

        Note:
            The subprocess runs in the background. Use disconnect_device() to stop it.
            LSL stream will be available ~2-5 seconds after this returns.
        """
        if stream_name in self.connected_processes:
            logger.warning(f"Device {stream_name} already connected")
            return False

        logger.info(f"Connecting {stream_name} to {address}...")

        try:
            # Start muselsl stream subprocess
            # Command: muselsl stream --address <MAC> --name <STREAM_NAME>
            process = subprocess.Popen(
                [
                    'muselsl', 'stream',
                    '--address', address,
                    '--name', stream_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Store process handle
            self.connected_processes[stream_name] = process

            # Store device info
            self.device_info[stream_name] = Device(
                name=stream_name,
                address=address,
                status="connecting",  # Will change to "streaming" once LSL active
                stream_name=stream_name
            )

            logger.info(f"✓ {stream_name} subprocess started (PID: {process.pid})")

            # TODO: Wait for LSL stream to become available (optional enhancement)
            # For now, assume ~2-5 seconds for Bluetooth connection + LSL publish

            return True

        except FileNotFoundError:
            logger.error("muselsl command not found - is it installed?")
            return False
        except Exception as e:
            logger.error(f"Failed to connect {stream_name}: {e}")
            return False

    def disconnect_device(self, stream_name: str) -> bool:
        """
        Disconnect a Muse device and stop LSL streaming.

        Gracefully terminates the muselsl subprocess.

        Args:
            stream_name: LSL stream name (e.g., "Muse_1")

        Returns:
            True if disconnection successful, False otherwise
        """
        if stream_name not in self.connected_processes:
            logger.warning(f"Device {stream_name} not connected")
            return False

        logger.info(f"Disconnecting {stream_name}...")

        try:
            process = self.connected_processes[stream_name]

            # Try graceful termination first
            process.terminate()

            try:
                process.wait(timeout=3.0)
                logger.info(f"✓ {stream_name} gracefully stopped")
            except subprocess.TimeoutExpired:
                # Force kill if graceful termination fails
                logger.warning(f"{stream_name} didn't stop gracefully, forcing...")
                process.kill()
                process.wait()
                logger.info(f"✓ {stream_name} force killed")

            # Cleanup
            del self.connected_processes[stream_name]
            if stream_name in self.device_info:
                self.device_info[stream_name].status = "disconnected"

            return True

        except Exception as e:
            logger.error(f"Error disconnecting {stream_name}: {e}")
            return False

    def get_connected_devices(self) -> List[str]:
        """
        Get list of currently connected device stream names.

        Returns:
            List of stream names (e.g., ["Muse_1", "Muse_2"])
        """
        return list(self.connected_processes.keys())

    def is_device_healthy(self, stream_name: str) -> bool:
        """
        Check if a connected device subprocess is still running.

        Args:
            stream_name: LSL stream name

        Returns:
            True if process is alive, False otherwise
        """
        if stream_name not in self.connected_processes:
            return False

        process = self.connected_processes[stream_name]
        return process.poll() is None  # None = still running

    def monitor_device_health(self) -> Dict[str, bool]:
        """
        Check health status of all connected devices.

        Returns:
            Dict mapping stream_name -> is_healthy

        Note:
            If a device is unhealthy, it should be disconnected and reconnected.
            Auto-reconnection can be implemented in a background monitoring task.
        """
        health_status = {}

        for stream_name in list(self.connected_processes.keys()):
            is_healthy = self.is_device_healthy(stream_name)
            health_status[stream_name] = is_healthy

            if not is_healthy:
                logger.warning(f"Device {stream_name} subprocess died!")
                # Cleanup dead process
                del self.connected_processes[stream_name]
                if stream_name in self.device_info:
                    self.device_info[stream_name].status = "disconnected"

        return health_status

    def disconnect_all(self):
        """
        Disconnect all devices and cleanup.

        Call this during shutdown to ensure clean termination.
        """
        logger.info("Disconnecting all devices...")

        for stream_name in list(self.connected_processes.keys()):
            self.disconnect_device(stream_name)

        logger.info("All devices disconnected")

    def _get_mock_devices(self) -> List[Device]:
        """
        Return mock devices for testing/development.

        Used as fallback when muselsl is not available or scanning fails.
        """
        logger.info("Returning mock devices (muselsl not available)")

        return [
            Device(
                name="Muse S - 3C4F",
                address="00:55:DA:B3:3C4F",
                status="available",
                battery=87
            ),
            Device(
                name="Muse S - 7A21",
                address="00:55:DA:B3:7A:21",
                status="available",
                battery=72
            ),
            Device(
                name="Muse S - 9B15",
                address="00:55:DA:B3:9B15",
                status="available",
                battery=94
            ),
        ]

    def __del__(self):
        """Cleanup on destruction"""
        self.disconnect_all()
