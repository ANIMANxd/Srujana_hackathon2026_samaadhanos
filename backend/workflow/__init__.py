"""Track state machines and workflow guards (architecture_v4 section 5).

`transitions.py` is the single action table; the routes and the fixture generator
both read it. Mutating workflow routes land here next.
"""

from backend.workflow.transitions import (
    ACTIONS,
    FINANCING_STATES_BEFORE_ASSIGNMENT,
    TERMINAL_STATES,
    available_actions,
    is_terminal,
    recovery_allowed,
)

__all__ = [
    "ACTIONS",
    "FINANCING_STATES_BEFORE_ASSIGNMENT",
    "TERMINAL_STATES",
    "available_actions",
    "is_terminal",
    "recovery_allowed",
]
