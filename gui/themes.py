from __future__ import annotations

import dearpygui.dearpygui as dpg

CONNECTED_THEME = "theme_button_connected"
DISCONNECTED_THEME = "theme_button_disconnected"
DANGER_THEME = "theme_button_danger"
SELECTED_HISTORY_ROW_THEME = "theme_selected_history_row"
HISTORY_SELECTABLE_THEME = "theme_history_selectable"
HISTORY_TABLE_THEME = "theme_history_table"
CONNECTIONS_READY_THEME = "theme_connections_ready"
CONNECTIONS_PENDING_THEME = "theme_connections_pending"


def create_button_themes() -> None:
    with dpg.theme(tag=CONNECTIONS_READY_THEME), dpg.theme_component(dpg.mvTab):
        for color, value in (
            (dpg.mvThemeCol_Tab, (38, 120, 68, 255)),
            (dpg.mvThemeCol_TabHovered, (52, 150, 82, 255)),
            (dpg.mvThemeCol_TabSelected, (45, 135, 76, 255)),
        ):
            dpg.add_theme_color(color, value, category=dpg.mvThemeCat_Core)

    with dpg.theme(tag=CONNECTIONS_PENDING_THEME), dpg.theme_component(dpg.mvTab):
        for color, value in (
            (dpg.mvThemeCol_Tab, (145, 92, 35, 255)),
            (dpg.mvThemeCol_TabHovered, (175, 116, 43, 255)),
            (dpg.mvThemeCol_TabSelected, (160, 102, 38, 255)),
        ):
            dpg.add_theme_color(color, value, category=dpg.mvThemeCat_Core)

    with dpg.theme(tag=CONNECTED_THEME), dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(
            dpg.mvThemeCol_Button,
            (46, 125, 50, 255),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_ButtonHovered,
            (67, 160, 71, 255),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_ButtonActive,
            (27, 94, 32, 255),
            category=dpg.mvThemeCat_Core,
        )

    with (
        dpg.theme(tag=DISCONNECTED_THEME),
        dpg.theme_component(dpg.mvButton),
    ):
        dpg.add_theme_color(
            dpg.mvThemeCol_Button,
            (80, 80, 80, 255),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_ButtonHovered,
            (105, 105, 105, 255),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_ButtonActive,
            (55, 55, 55, 255),
            category=dpg.mvThemeCat_Core,
        )

    with dpg.theme(tag=HISTORY_TABLE_THEME), dpg.theme_component(dpg.mvTable):
        dpg.add_theme_color(
            dpg.mvThemeCol_Header,
            (0, 0, 0, 0),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_HeaderActive,
            (0, 0, 0, 0),
            category=dpg.mvThemeCat_Core,
        )

    with dpg.theme(tag=HISTORY_SELECTABLE_THEME), dpg.theme_component(dpg.mvSelectable):
        dpg.add_theme_color(
            dpg.mvThemeCol_HeaderHovered,
            (58, 105, 160, 180),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_HeaderActive,
            (45, 84, 130, 210),
            category=dpg.mvThemeCat_Core,
        )

    with dpg.theme(tag=SELECTED_HISTORY_ROW_THEME), dpg.theme_component(dpg.mvTableRow):
        dpg.add_theme_color(
            dpg.mvThemeCol_TableRowBg,
            (45, 84, 130, 210),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_TableRowBgAlt,
            (45, 84, 130, 210),
            category=dpg.mvThemeCat_Core,
        )

    with dpg.theme(tag=DANGER_THEME), dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(
            dpg.mvThemeCol_Button,
            (198, 40, 40, 255),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_ButtonHovered,
            (229, 75, 75, 255),
            category=dpg.mvThemeCat_Core,
        )
        dpg.add_theme_color(
            dpg.mvThemeCol_ButtonActive,
            (139, 0, 0, 255),
            category=dpg.mvThemeCat_Core,
        )


def set_connections_tab_visual(ready: bool) -> None:
    """Color the connections tab according to the complete device state."""
    if not dpg.does_item_exist("connections_tab"):
        return
    dpg.bind_item_theme(
        "connections_tab",
        CONNECTIONS_READY_THEME if ready else CONNECTIONS_PENDING_THEME,
    )


def set_connection_button_visual(
    tag: str,
    connected: bool,
    connected_label: str,
    disconnected_label: str,
) -> None:
    if not dpg.does_item_exist(tag):
        return

    dpg.configure_item(
        tag,
        label=connected_label if connected else disconnected_label,
    )
    dpg.bind_item_theme(
        tag,
        CONNECTED_THEME if connected else DISCONNECTED_THEME,
    )
