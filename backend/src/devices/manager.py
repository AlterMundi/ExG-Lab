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

Environment Variables:
- MUSELSL_PATH: Custom path to muselsl binary (default: system PATH)
- EXG_REQUIRE_HARDWARE: Raise error if no real devices found (default: true)
"""

import subprocess
import logging
import time
import re
import os
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
        """
        Initialize device manager with hardware validation.

        Raises:
            RuntimeError: If muselsl is not available and EXG_REQUIRE_HARDWARE=true
        """
        self.connected_processes: Dict[str, subprocess.Popen] = {}
        self.device_info: Dict[str, Device] = {}

        # Get muselsl path
        # Try venv first (if running from venv), then fall back to system PATH
        import sys
        venv_muselsl = os.path.join(os.path.dirname(sys.executable), 'muselsl')
        if os.path.exists(venv_muselsl):
            self.muselsl_cmd = venv_muselsl
        else:
            self.muselsl_cmd = os.environ.get('MUSELSL_PATH', 'muselsl')

        # Check if hardware is required (default: true for production)
        self.require_hardware = os.environ.get('EXG_REQUIRE_HARDWARE', 'true').lower() == 'true'

        # Validate muselsl availability
        self._validate_muselsl()

        logger.info("DeviceManager initialized")

    def _validate_muselsl(self):
        """
        Validate that muselsl is available and check version.

        Raises:
            RuntimeError: If muselsl not found and hardware is required
        """
        try:
            # Check if muselsl is available
            result = subprocess.run(
                [self.muselsl_cmd, '--version'],
                capture_output=True,
                text=True,
                timeout=5.0
            )

            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"muselsl found: {version}")

                # Warn about known buggy versions
                if '2.2.2' in version:
                    logger.warning(
                        "muselsl v2.2.2 has known bugs (bluetoothctl EOF handling). "
                        "See docs/07-muselsl-bugfixes.md for workarounds."
                    )
            else:
                logger.warning(f"muselsl version check failed: {result.stderr}")

        except FileNotFoundError:
            error_msg = (
                f"muselsl not found at '{self.muselsl_cmd}'. "
                "Install with: pip install muselsl\n"
                "Or set custom path: export MUSELSL_PATH=/path/to/muselsl\n"
                "For development without hardware: export EXG_REQUIRE_HARDWARE=false"
            )

            if self.require_hardware:
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                logger.warning(f"{error_msg}\nContinuing in development mode (hardware not required)")

        except Exception as e:
            logger.warning(f"muselsl validation failed: {e}")

    def scan_devices(self, timeout: float = 5.0) -> List[Device]:
        """
        Scan for available Muse devices using muselsl list.

        Args:
            timeout: Scan timeout in seconds

        Returns:
            List of discovered Device objects

        Raises:
            RuntimeError: If muselsl is not available (only if EXG_REQUIRE_HARDWARE=true)

        Note:
            This wraps `muselsl list` which has known bugs in v2.2.2:
            - May fail with EOF error on some systems
            - See docs/07-muselsl-bugfixes.md for workarounds
        """
        logger.info(f"Scanning for Muse devices (timeout={timeout}s)...")

        try:
            # Run muselsl list command
            result = subprocess.run(
                [self.muselsl_cmd, 'list'],
                capture_output=True,
                text=True,
                timeout=timeout + 2,  # Extra buffer for process overhead
            )

            if result.returncode != 0:
                error_msg = f"muselsl list failed (exit code {result.returncode}): {result.stderr}"
                logger.error(error_msg)

                # Check if it's a Bluetooth issue
                if 'bluetooth' in result.stderr.lower() or 'hci' in result.stderr.lower():
                    logger.error(
                        "Bluetooth may not be enabled. Try:\n"
                        "  sudo systemctl start bluetooth\n"
                        "  sudo bluetoothctl power on"
                    )

                if self.require_hardware:
                    raise RuntimeError(error_msg)
                else:
                    logger.warning("Returning empty device list (development mode)")
                    return []

            # Parse output
            devices = self._parse_muselsl_list_output(result.stdout)
            logger.info(f"Found {len(devices)} Muse device(s)")

            if len(devices) == 0:
                logger.warning(
                    "No Muse devices found. Make sure:\n"
                    "  1. Muse headband is turned on (LED should be solid white/blue)\n"
                    "  2. Bluetooth is enabled on your system\n"
                    "  3. Device is in pairing mode (hold power button for 5 seconds)"
                )

            return devices

        except subprocess.TimeoutExpired:
            error_msg = f"Device scan timed out after {timeout}s"
            logger.error(error_msg)

            if self.require_hardware:
                raise RuntimeError(error_msg)
            else:
                logger.warning("Returning empty device list (development mode)")
                return []

        except FileNotFoundError:
            error_msg = (
                f"muselsl command not found at '{self.muselsl_cmd}'. "
                "This should have been caught in _validate_muselsl()"
            )
            logger.error(error_msg)

            if self.require_hardware:
                raise RuntimeError(error_msg)
            else:
                logger.warning("Returning empty device list (development mode)")
                return []

        except Exception as e:
            error_msg = f"Device scan error: {e}"
            logger.error(error_msg)

            if self.require_hardware:
                raise RuntimeError(error_msg)
            else:
                logger.warning("Returning empty device list (development mode)")
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
                    self.muselsl_cmd, 'stream',
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

    def __del__(self):
        """Cleanup on destruction"""
        self.disconnect_all()
