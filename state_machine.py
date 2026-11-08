"""
Explicit Finite State Machine (FSM) Engine for Muzziko Music Bot.
Defines typed states and validated lifecycle transitions for user interactions and download jobs.
"""

from enum import Enum
from typing import Set, Dict


class InvalidStateTransitionError(Exception):
    """Raised when an illegal FSM transition is attempted."""
    pass


class DownloadJobState(Enum):
    INITIALIZED = "INITIALIZED"
    SEARCHING = "SEARCHING"
    EXTRACTING_AUDIO = "EXTRACTING_AUDIO"
    TAGGING_METADATA = "TAGGING_METADATA"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class UserInteractionState(Enum):
    IDLE = "IDLE"
    SEARCH_DISPLAYED = "SEARCH_DISPLAYED"
    PAGINATING = "PAGINATING"
    DOWNLOADING = "DOWNLOADING"
    LYRICS_DISPLAYED = "LYRICS_DISPLAYED"
    CANCELLED = "CANCELLED"


class DownloadJobFSM:
    """Explicit FSM governing a track download lifecycle."""

    _VALID_TRANSITIONS: Dict[DownloadJobState, Set[DownloadJobState]] = {
        DownloadJobState.INITIALIZED: {
            DownloadJobState.SEARCHING,
            DownloadJobState.EXTRACTING_AUDIO,
            DownloadJobState.FAILED,
        },
        DownloadJobState.SEARCHING: {
            DownloadJobState.EXTRACTING_AUDIO,
            DownloadJobState.FAILED,
        },
        DownloadJobState.EXTRACTING_AUDIO: {
            DownloadJobState.TAGGING_METADATA,
            DownloadJobState.FAILED,
        },
        DownloadJobState.TAGGING_METADATA: {
            DownloadJobState.UPLOADING,
            DownloadJobState.COMPLETED,
            DownloadJobState.FAILED,
        },
        DownloadJobState.UPLOADING: {
            DownloadJobState.COMPLETED,
            DownloadJobState.FAILED,
        },
        DownloadJobState.COMPLETED: set(),
        DownloadJobState.FAILED: set(),
    }

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._state = DownloadJobState.INITIALIZED

    @property
    def current_state(self) -> DownloadJobState:
        return self._state

    def transition_to(self, new_state: DownloadJobState, reason: str = "") -> None:
        if new_state == self._state:
            return
        allowed = self._VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Job [{self.task_id}] illegal transition from {self._state.value} to {new_state.value} ({reason})"
            )
        self._state = new_state


class UserInteractionFSM:
    """Explicit FSM governing user session interaction lifecycle."""

    _VALID_TRANSITIONS: Dict[UserInteractionState, Set[UserInteractionState]] = {
        UserInteractionState.IDLE: {
            UserInteractionState.SEARCH_DISPLAYED,
            UserInteractionState.DOWNLOADING,
            UserInteractionState.LYRICS_DISPLAYED,
        },
        UserInteractionState.SEARCH_DISPLAYED: {
            UserInteractionState.PAGINATING,
            UserInteractionState.DOWNLOADING,
            UserInteractionState.LYRICS_DISPLAYED,
            UserInteractionState.CANCELLED,
            UserInteractionState.IDLE,
        },
        UserInteractionState.PAGINATING: {
            UserInteractionState.PAGINATING,
            UserInteractionState.DOWNLOADING,
            UserInteractionState.LYRICS_DISPLAYED,
            UserInteractionState.CANCELLED,
            UserInteractionState.IDLE,
        },
        UserInteractionState.DOWNLOADING: {
            UserInteractionState.IDLE,
            UserInteractionState.SEARCH_DISPLAYED,
        },
        UserInteractionState.LYRICS_DISPLAYED: {
            UserInteractionState.IDLE,
            UserInteractionState.SEARCH_DISPLAYED,
            UserInteractionState.DOWNLOADING,
            UserInteractionState.CANCELLED,
        },
        UserInteractionState.CANCELLED: {
            UserInteractionState.IDLE,
            UserInteractionState.SEARCH_DISPLAYED,
        },
    }

    def __init__(self, user_id: int):
        self.user_id = user_id
        self._state = UserInteractionState.IDLE

    @property
    def current_state(self) -> UserInteractionState:
        return self._state

    def transition_to(self, new_state: UserInteractionState, reason: str = "") -> None:
        if new_state == self._state:
            return
        allowed = self._VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"User [{self.user_id}] illegal transition from {self._state.value} to {new_state.value} ({reason})"
            )
        self._state = new_state
