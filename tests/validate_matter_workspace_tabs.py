"""Validate that every matter sub-tab renders the data it stores.

The matter workspace mirrors the Judiciary e-filing portal's case-detail tabs:
Summary, Parties, Activities, Lodgings, Court Decisions, Fees, Receipts,
Documents. The backend implemented all of them, but only Fees and Receipts were
ever repopulated in the UI -- adding a party wrote a row to SQLite and left the
tab showing its placeholder string, so the data was persisted and invisible.

This asserts the round trip for each tab: add through the visible control, then
find the new row rendered in that tab's list.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QListWidget, QPushButton, QTabWidget  # noqa: E402

from ui import MainWindow, create_app  # noqa: E402
from ui.app import DEV_UNLOCK_ENV_VAR, MATTER_TAB_VIEWS  # noqa: E402

# Tabs whose "Add" control creates a row. Documents are added by upload, which
# the evidence runners cover end to end with real files.
ADDABLE_TABS = (
    "partiesTab",
    "activitiesTab",
    "lodgingsTab",
    "courtDecisionsTab",
    "feesTab",
    "receiptsTab",
    "filingRecordTab",
)


def main() -> None:
    os.environ[DEV_UNLOCK_ENV_VAR] = "1"
    try:
        app = create_app(["validate_matter_workspace_tabs"])
        with tempfile.TemporaryDirectory() as temp_dir:
            window = MainWindow(workspace=Path(temp_dir) / "firm")

            def button(name: str) -> QPushButton:
                found = window.findChild(QPushButton, name)
                assert found is not None, name
                return found

            def listing(object_name: str) -> QListWidget:
                found = window.findChild(QListWidget, f"{object_name}List")
                assert found is not None, object_name
                return found

            button("startSoloButton").click()
            app.processEvents()
            assert window._backend_local is not None

            # Every tab in the table must exist in the widget tree, and the
            # workspace must expose them in the portal's order.
            tabs = window.findChild(QTabWidget, "matterWorkspaceTabs")
            assert tabs is not None
            assert [tabs.tabText(i) for i in range(tabs.count())] == [
                "Summary",
                *[view.label for view in MATTER_TAB_VIEWS],
            ]

            button("newMatterButton").click()
            app.processEvents()
            assert window._current_matter_id

            for object_name in ADDABLE_TABS:
                before = [
                    listing(object_name).item(i).text() for i in range(listing(object_name).count())
                ]
                button(f"{object_name}AddButton").click()
                app.processEvents()
                after = [
                    listing(object_name).item(i).text() for i in range(listing(object_name).count())
                ]
                assert after != before, (
                    f"{object_name} did not change after Add; the tab is not "
                    f"reading back what the backend stored"
                )
                view = next(v for v in MATTER_TAB_VIEWS if v.object_name == object_name)
                assert view.empty_text not in after, (
                    f"{object_name} still shows its placeholder after Add: {after}"
                )
                assert all(text.strip() for text in after), f"{object_name} rendered a blank row"

            # Selecting a matter from the list opens it and repopulates the tabs.
            created_matter_id = window._current_matter_id
            parties_after_add = [
                listing("partiesTab").item(i).text() for i in range(listing("partiesTab").count())
            ]
            window._current_matter_id = ""
            matter_list = window.findChild(QListWidget, "matterList")
            assert matter_list is not None
            button("refreshMatterListButton").click()
            app.processEvents()
            assert matter_list.count() >= 1
            matter_list.setCurrentRow(0)
            app.processEvents()
            assert window._current_matter_id == created_matter_id, (
                "selecting a matter did not open it"
            )
            reopened = [
                listing("partiesTab").item(i).text() for i in range(listing("partiesTab").count())
            ]
            assert reopened == parties_after_add, (reopened, parties_after_add)

            window.close()
            app.processEvents()
    finally:
        os.environ.pop(DEV_UNLOCK_ENV_VAR, None)

    print(
        f"MATTER WORKSPACE TABS VALIDATION PASS: {len(MATTER_TAB_VIEWS)} tabs render backend data"
    )


if __name__ == "__main__":
    main()
