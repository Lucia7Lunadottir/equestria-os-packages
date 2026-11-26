"""System Recovery — embeds equestria-os-recovery (образ восстановления в меню GRUB)."""

from embedded_module import EmbeddedAppModule


class RecoveryModule(EmbeddedAppModule):
    module_id        = "mod_recovery"
    display_name_key = "module.recovery.name"
    description_key  = "module.recovery.desc"
    category         = "system"
    icon             = "🛟"
    sort_order       = 36
    required_binary  = "/usr/bin/equestria-recovery"
    package_name     = "equestria-os-recovery"

    lib_dir    = "/opt/equestria-os/equestria-os-recovery"
    main_file  = "recovery_manager.py"
    main_class = "RecoveryManagerApp"
