"""
Session Manager - Experimental session lifecycle and configuration

This module manages neurofeedback experimental sessions:
- Session lifecycle (start, stop, pause, resume)
- Protocol configuration and validation
- Metadata tracking (subject IDs, timestamps, notes)
- Device-session coordination
- Data recording orchestration

Session Phases:
1. IDLE: No session active
2. BASELINE: Pre-feedback baseline recording (e.g., 2 minutes eyes-closed)
3. TRAINING: Active neurofeedback training
4. COOLDOWN: Post-training baseline (e.g., 2 minutes eyes-closed)
5. PAUSED: Session temporarily suspended
6. COMPLETED: Session finished, data saved

Protocol Structure:
- Name: "Meditation Baseline", "Neurofeedback Training", etc.
- Description: Purpose and instructions
- Phases: List of timed phases with instructions
- Devices: List of required device names/subjects
- Feedback: Configuration for real-time feedback

Usage:
    session_manager = SessionManager(
        devices=['Muse_1', 'Muse_2'],
        data_recorder=data_recorder
    )

    # Start session
    session_id = session_manager.start_session(
        protocol_name="Meditation Baseline",
        subject_ids={'Muse_1': 'P001', 'Muse_2': 'P002'},
        notes="First meditation session"
    )

    # Check status
    status = session_manager.get_session_status()

    # Stop session
    session_manager.stop_session()
"""

import logging
import time
import uuid
from typing import Dict, List, Optional, Set
from enum import Enum
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class SessionPhase(Enum):
    """Session lifecycle phases"""
    IDLE = "idle"
    BASELINE = "baseline"
    TRAINING = "training"
    COOLDOWN = "cooldown"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass
class ProtocolPhase:
    """
    Single phase within an experimental protocol.

    Example: 2-minute baseline, 10-minute training, 2-minute cooldown
    """
    name: str
    duration_seconds: float
    instructions: str
    feedback_enabled: bool = False


@dataclass
class ExperimentalProtocol:
    """
    Complete experimental protocol specification.

    Defines the structure, timing, and configuration for a session.
    """
    name: str
    description: str
    phases: List[ProtocolPhase]
    min_devices: int = 1
    max_devices: int = 4
    feedback_config: Dict = field(default_factory=dict)

    def total_duration(self) -> float:
        """Get total protocol duration in seconds"""
        return sum(phase.duration_seconds for phase in self.phases)

    def validate(self) -> List[str]:
        """
        Validate protocol configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.name:
            errors.append("Protocol name is required")

        if not self.phases:
            errors.append("Protocol must have at least one phase")

        if self.min_devices < 1:
            errors.append("min_devices must be >= 1")

        if self.max_devices < self.min_devices:
            errors.append("max_devices must be >= min_devices")

        for i, phase in enumerate(self.phases):
            if phase.duration_seconds <= 0:
                errors.append(f"Phase {i} ({phase.name}) must have positive duration")

        return errors


@dataclass
class SessionConfig:
    """
    Configuration for a specific session instance.

    Links devices to subjects and provides session metadata.
    """
    session_id: str
    protocol: ExperimentalProtocol
    subject_ids: Dict[str, str]  # device_name -> subject_id (e.g., 'Muse_1' -> 'P001')
    start_time: float
    notes: str = ""
    experimenter: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class SessionStatus:
    """
    Current session status for monitoring.

    Provides real-time information about session progress.
    """
    is_active: bool
    session_id: Optional[str]
    protocol_name: Optional[str]
    current_phase: SessionPhase
    phase_name: Optional[str]
    elapsed_seconds: float
    remaining_seconds: Optional[float]
    devices: List[str]
    subject_ids: Dict[str, str]


# Built-in protocols
BUILTIN_PROTOCOLS = {
    'meditation_baseline': ExperimentalProtocol(
        name="Meditation Baseline",
        description="Simple baseline recording with eyes closed meditation",
        phases=[
            ProtocolPhase(
                name="Baseline",
                duration_seconds=120.0,  # 2 minutes
                instructions="Sit comfortably with eyes closed. Focus on your breath.",
                feedback_enabled=False
            ),
            ProtocolPhase(
                name="Training",
                duration_seconds=600.0,  # 10 minutes
                instructions="Continue meditating. The feedback will guide you toward a relaxed state.",
                feedback_enabled=True
            ),
            ProtocolPhase(
                name="Cooldown",
                duration_seconds=120.0,  # 2 minutes
                instructions="Final baseline. Eyes closed, natural breathing.",
                feedback_enabled=False
            )
        ],
        min_devices=1,
        max_devices=4,
        feedback_config={
            'target_metric': 'relaxation',
            'target_threshold': 1.5,
            'timescale': '4s'
        }
    ),
    'quick_test': ExperimentalProtocol(
        name="Quick Test",
        description="Short test session for validation (30 seconds)",
        phases=[
            ProtocolPhase(
                name="Test",
                duration_seconds=30.0,
                instructions="Short test with feedback enabled",
                feedback_enabled=True
            )
        ],
        min_devices=1,
        max_devices=4,
        feedback_config={
            'target_metric': 'relaxation',
            'target_threshold': 1.5,
            'timescale': '4s'
        }
    ),
    'eyes_open_closed': ExperimentalProtocol(
        name="Eyes Open/Closed",
        description="Classic EEG paradigm for validating alpha rhythm",
        phases=[
            ProtocolPhase(
                name="Eyes Open",
                duration_seconds=60.0,
                instructions="Keep eyes open, looking at a fixed point",
                feedback_enabled=False
            ),
            ProtocolPhase(
                name="Eyes Closed 1",
                duration_seconds=60.0,
                instructions="Close eyes and relax",
                feedback_enabled=False
            ),
            ProtocolPhase(
                name="Eyes Open 2",
                duration_seconds=60.0,
                instructions="Open eyes, looking at a fixed point",
                feedback_enabled=False
            ),
            ProtocolPhase(
                name="Eyes Closed 2",
                duration_seconds=60.0,
                instructions="Close eyes and relax",
                feedback_enabled=False
            )
        ],
        min_devices=1,
        max_devices=4,
        feedback_config={}
    )
}


class SessionManager:
    """
    Manages experimental session lifecycle and coordination.

    Coordinates:
    - Session configuration and validation
    - Device-subject mapping
    - Data recording orchestration
    - Phase transitions and timing
    """

    def __init__(
        self,
        devices: List[str],
        data_recorder: Optional['DataRecorder'] = None
    ):
        """
        Initialize session manager.

        Args:
            devices: List of available device names (e.g., ['Muse_1', 'Muse_2'])
            data_recorder: DataRecorder instance for CSV export (optional)
        """
        self.devices = devices
        self.data_recorder = data_recorder

        # Current session state
        self.current_session: Optional[SessionConfig] = None
        self.current_phase: SessionPhase = SessionPhase.IDLE
        self.phase_start_time: Optional[float] = None
        self.phase_index: int = 0

        # Protocol library
        self.protocols: Dict[str, ExperimentalProtocol] = BUILTIN_PROTOCOLS.copy()

        logger.info(f"SessionManager initialized with {len(devices)} devices")

    def add_protocol(self, protocol: ExperimentalProtocol) -> bool:
        """
        Add custom protocol to library.

        Args:
            protocol: ExperimentalProtocol instance

        Returns:
            True if added successfully, False if validation fails
        """
        errors = protocol.validate()
        if errors:
            logger.error(f"Protocol validation failed: {errors}")
            return False

        protocol_key = protocol.name.lower().replace(' ', '_')
        self.protocols[protocol_key] = protocol
        logger.info(f"Protocol '{protocol.name}' added to library")
        return True

    def get_protocol(self, protocol_name: str) -> Optional[ExperimentalProtocol]:
        """
        Get protocol by name.

        Args:
            protocol_name: Protocol name (case-insensitive, spaces converted to underscores)

        Returns:
            ExperimentalProtocol instance or None if not found
        """
        protocol_key = protocol_name.lower().replace(' ', '_')
        return self.protocols.get(protocol_key)

    def list_protocols(self) -> List[Dict]:
        """
        List all available protocols.

        Returns:
            List of protocol summaries with name, description, duration, phases
        """
        return [
            {
                'name': p.name,
                'description': p.description,
                'duration_seconds': p.total_duration(),
                'num_phases': len(p.phases),
                'min_devices': p.min_devices,
                'max_devices': p.max_devices
            }
            for p in self.protocols.values()
        ]

    def start_session(
        self,
        protocol_name: str,
        subject_ids: Dict[str, str],
        notes: str = "",
        experimenter: str = ""
    ) -> Optional[str]:
        """
        Start new experimental session.

        Args:
            protocol_name: Name of protocol to run
            subject_ids: Dict mapping device_name -> subject_id (e.g., {'Muse_1': 'P001'})
            notes: Optional session notes
            experimenter: Optional experimenter name

        Returns:
            Session ID (UUID) if successful, None if failed
        """
        # Check if session already active
        if self.current_session is not None:
            logger.error("Cannot start session - session already active")
            return None

        # Get protocol
        protocol = self.get_protocol(protocol_name)
        if protocol is None:
            logger.error(f"Protocol '{protocol_name}' not found")
            return None

        # Validate device count
        n_devices = len(subject_ids)
        if n_devices < protocol.min_devices or n_devices > protocol.max_devices:
            logger.error(
                f"Protocol requires {protocol.min_devices}-{protocol.max_devices} devices, "
                f"got {n_devices}"
            )
            return None

        # Validate devices exist
        for device_name in subject_ids.keys():
            if device_name not in self.devices:
                logger.error(f"Device '{device_name}' not available")
                return None

        # Create session config
        session_id = str(uuid.uuid4())
        start_time = time.time()

        self.current_session = SessionConfig(
            session_id=session_id,
            protocol=protocol,
            subject_ids=subject_ids,
            start_time=start_time,
            notes=notes,
            experimenter=experimenter,
            metadata={
                'devices': list(subject_ids.keys()),
                'protocol_key': protocol_name.lower().replace(' ', '_')
            }
        )

        # Start recording if data recorder available
        if self.data_recorder:
            recording_started = self.data_recorder.start_recording(
                session_id=session_id,
                subject_ids=subject_ids,
                metadata={
                    'protocol': protocol.name,
                    'notes': notes,
                    'experimenter': experimenter,
                    'start_time': datetime.fromtimestamp(start_time).isoformat()
                }
            )
            if not recording_started:
                logger.warning("Failed to start data recording")

        # Transition to first phase
        self.phase_index = 0
        self.phase_start_time = time.time()

        # Determine initial phase type
        first_phase = protocol.phases[0]
        if 'baseline' in first_phase.name.lower():
            self.current_phase = SessionPhase.BASELINE
        elif 'training' in first_phase.name.lower():
            self.current_phase = SessionPhase.TRAINING
        else:
            self.current_phase = SessionPhase.BASELINE  # Default

        logger.info(
            f"✓ Session started: {session_id} | Protocol: {protocol.name} | "
            f"Devices: {list(subject_ids.keys())}"
        )

        return session_id

    def stop_session(self) -> bool:
        """
        Stop current session and finalize recording.

        Returns:
            True if stopped successfully, False if no session active
        """
        if self.current_session is None:
            logger.warning("No active session to stop")
            return False

        session_id = self.current_session.session_id

        # Stop recording
        if self.data_recorder:
            files = self.data_recorder.stop_recording()
            logger.info(f"Recording saved: {files}")

        # Transition to completed
        self.current_phase = SessionPhase.COMPLETED

        # Clear session state
        logger.info(f"✓ Session stopped: {session_id}")
        self.current_session = None
        self.phase_start_time = None
        self.phase_index = 0
        self.current_phase = SessionPhase.IDLE

        return True

    def pause_session(self) -> bool:
        """Pause current session"""
        if self.current_session is None:
            return False

        self.current_phase = SessionPhase.PAUSED
        logger.info(f"Session paused: {self.current_session.session_id}")
        return True

    def resume_session(self) -> bool:
        """Resume paused session"""
        if self.current_session is None or self.current_phase != SessionPhase.PAUSED:
            return False

        # Restore previous phase
        current = self.current_session.protocol.phases[self.phase_index]
        if 'baseline' in current.name.lower():
            self.current_phase = SessionPhase.BASELINE
        elif 'training' in current.name.lower():
            self.current_phase = SessionPhase.TRAINING
        else:
            self.current_phase = SessionPhase.TRAINING

        logger.info(f"Session resumed: {self.current_session.session_id}")
        return True

    def update_phase(self) -> bool:
        """
        Check if current phase is complete and advance to next.

        Should be called periodically (e.g., every second) to handle transitions.

        Returns:
            True if phase changed, False otherwise
        """
        if self.current_session is None or self.phase_start_time is None:
            return False

        # Check if phase duration exceeded
        elapsed = time.time() - self.phase_start_time
        current_phase_config = self.current_session.protocol.phases[self.phase_index]

        if elapsed >= current_phase_config.duration_seconds:
            # Advance to next phase
            self.phase_index += 1

            # Check if session complete
            if self.phase_index >= len(self.current_session.protocol.phases):
                logger.info("Session complete - all phases finished")
                self.stop_session()
                return True

            # Transition to next phase
            next_phase = self.current_session.protocol.phases[self.phase_index]
            self.phase_start_time = time.time()

            # Update phase type
            if 'baseline' in next_phase.name.lower():
                self.current_phase = SessionPhase.BASELINE
            elif 'training' in next_phase.name.lower():
                self.current_phase = SessionPhase.TRAINING
            elif 'cooldown' in next_phase.name.lower():
                self.current_phase = SessionPhase.COOLDOWN
            else:
                self.current_phase = SessionPhase.TRAINING

            logger.info(f"Phase transition: {next_phase.name} ({self.current_phase.value})")
            return True

        return False

    def get_session_status(self) -> SessionStatus:
        """
        Get current session status.

        Returns:
            SessionStatus with current progress and configuration
        """
        if self.current_session is None:
            return SessionStatus(
                is_active=False,
                session_id=None,
                protocol_name=None,
                current_phase=SessionPhase.IDLE,
                phase_name=None,
                elapsed_seconds=0.0,
                remaining_seconds=None,
                devices=[],
                subject_ids={}
            )

        # Compute timing
        total_elapsed = time.time() - self.current_session.start_time
        phase_elapsed = time.time() - self.phase_start_time if self.phase_start_time else 0.0

        current_phase_config = self.current_session.protocol.phases[self.phase_index]
        phase_remaining = current_phase_config.duration_seconds - phase_elapsed

        # Total remaining across all future phases
        total_remaining = phase_remaining
        for i in range(self.phase_index + 1, len(self.current_session.protocol.phases)):
            total_remaining += self.current_session.protocol.phases[i].duration_seconds

        return SessionStatus(
            is_active=True,
            session_id=self.current_session.session_id,
            protocol_name=self.current_session.protocol.name,
            current_phase=self.current_phase,
            phase_name=current_phase_config.name,
            elapsed_seconds=total_elapsed,
            remaining_seconds=total_remaining,
            devices=list(self.current_session.subject_ids.keys()),
            subject_ids=self.current_session.subject_ids
        )

    def is_feedback_enabled(self) -> bool:
        """
        Check if feedback should be shown in current phase.

        Returns:
            True if feedback enabled for current phase
        """
        if self.current_session is None:
            return False

        current_phase_config = self.current_session.protocol.phases[self.phase_index]
        return current_phase_config.feedback_enabled

    def get_current_instructions(self) -> Optional[str]:
        """
        Get instructions for current phase.

        Returns:
            Instructions string or None if no session active
        """
        if self.current_session is None:
            return None

        current_phase_config = self.current_session.protocol.phases[self.phase_index]
        return current_phase_config.instructions
