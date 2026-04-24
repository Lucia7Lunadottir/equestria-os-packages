"""Task Panel Changer — embeds the real equestria-os-task-panel-changer UI."""

from embedded_module import EmbeddedAppModule


class TaskPanelModule(EmbeddedAppModule):
    module_id = "mod_task_panel"
    display_name_key = "module.task_panel.name"
    description_key = "module.task_panel.desc"
    category = "appearance"
    icon = "📐"
    sort_order = 20
    required_binary = "/usr/bin/equestria-os-task-panel-changer"
    package_name = "equestria-os-task-panel-changer"

    lib_dir = "/opt/equestria-os/equestria-os-task-panel-changer"
    main_file = "main.py"
    main_class = "TaskPanelApp"
