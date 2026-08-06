"""Automation seam for driving the packaged application.

Testing the packaged executable through Windows UI Automation hits two walls.

Native file dialogs cannot be driven reliably: they are OS-owned, they block
Qt's event loop while open, and a picker that fails to close stalls every
subsequent query. So a whole class of behaviour -- opening a matter from a
document, importing files -- could not be tested where it actually matters, in
the shipped binary.

And there is no way to ask the application what it believes. A harness left
scraping label text infers state from prose written for humans, which is how a
run reports "Navigate: Settings" as a pass and then finds nothing on the page.

This module answers both, and only when explicitly switched on:

* ``select_files()`` returns a queued selection instead of opening a picker.
* ``write_state()`` publishes a JSON snapshot of what the window holds.

Both are inert unless ``JURISNURU_AUTOMATION=1``. Neither weakens the licence
gate: activation still verifies a real signature, and the state file is a
read-only view. The seam automates the parts of a session a human would do with
a mouse; it does not grant anything a human could not do.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

AUTOMATION_ENV_VAR = "JURISNURU_AUTOMATION"
QUEUE_ENV_VAR = "JURISNURU_AUTOMATION_FILES"
STATE_ENV_VAR = "JURISNURU_AUTOMATION_STATE"


def automation_enabled() -> bool:
    """Whether the application is being driven by an automated harness."""
    return os.environ.get(AUTOMATION_ENV_VAR) == "1"


def queued_selection() -> list[str]:
    """Consume the next queued file selection, if automation is driving.

    The queue is a newline-delimited file. Each read takes the first line and
    rewrites the rest, so consecutive dialogs get consecutive selections and a
    harness cannot accidentally reuse a stale path.
    """
    if not automation_enabled():
        return []
    queue_path = os.environ.get(QUEUE_ENV_VAR, "")
    if not queue_path:
        return []
    path = Path(queue_path)
    if not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    entries = [line for line in lines if line]
    if not entries:
        return []
    selection, rest = entries[0], entries[1:]
    path.write_text("\n".join(rest), encoding="utf-8")
    # One line may hold several paths, for the multi-select dialogs.
    return [part for part in selection.split("|") if part]


def write_state(state: dict[str, object]) -> None:
    """Publish a snapshot of the window's state for a harness to assert on."""
    if not automation_enabled():
        return
    state_path = os.environ.get(STATE_ENV_VAR, "")
    if not state_path:
        return
    try:
        Path(state_path).write_text(
            json.dumps(state, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
    except OSError:
        # A harness reading mid-write gets the previous snapshot; never let
        # publishing state break the application it is observing.
        pass
