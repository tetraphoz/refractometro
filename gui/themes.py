from __future__ import annotations

import dearpygui.dearpygui as dpg

CONNECTED_THEME = "theme_button_connected"
DISCONNECTED_THEME = "theme_button_disconnected"
DANGER_THEME = "theme_button_danger"


def create_button_themes() -> None:
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
