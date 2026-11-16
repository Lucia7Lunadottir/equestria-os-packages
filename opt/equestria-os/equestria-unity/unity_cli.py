"""The Unity CLI: the only place that knows its commands and flags. Pages ask for an operation by name."""
from pathlib import Path

import unity_paths
from cli_errors import explain
from kit import tr

# Seconds a command may take before it is stopped: a Unity service that does not answer must not leave the
# launcher waiting forever. Downloads, installs and signing in have no limit (they can be cancelled instead).
STATUS, CATALOG, ACCOUNT = 30, 90, 120


class UnityCli:
    def __init__(self, jobs, config):
        self.jobs = jobs
        self.config = config

    @staticmethod
    def executable():
        return unity_paths.executable("unity")

    def run(self, key, title, arguments, done=None, *, structured=False, capture=False, failed=None,
            quiet=False, progress=False, queue=False, timeout=0):
        cli = self.executable()
        if not cli:
            if not quiet:
                self.jobs.message.emit(str(tr("cli.hint")))
            if failed:
                failed(tr("cli.hint"))
            return
        args = ["--no-pager", "--no-color"]
        if arguments[:2] != ["auth", "login"]:
            args.append("--non-interactive")
        if structured:
            args += ["--format", "json"]
        explained = (lambda reason: failed(explain(reason, timeout))) if failed else None
        self.jobs.run_process(key, title, cli, args + arguments, done, structured=structured, capture=capture,
                              failed=explained, environment=self.environment(), quiet=quiet, progress=progress,
                              queue=queue, timeout=timeout)

    def environment(self):
        """Launcher settings that reach the Unity CLI through its environment."""
        env = {}
        folder = self.config.get("download_dir")
        if folder:
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
                env.update(TMPDIR=folder, TMP=folder, TEMP=folder)  # the CLI downloads into the temp directory
            except OSError as error:
                self.jobs.message.emit(str(error))
        retries = self.config.get("install_retries")
        if isinstance(retries, int) and retries >= 0:
            env["UNITY_INSTALL_RETRIES"] = str(retries)
        return env

    # ---- Editors ----------------------------------------------------------------------------------

    @staticmethod
    def install_arguments(version, modules, *, installed, eula):
        """Install a new Editor, or add modules to an installed one."""
        args = ["install-modules", "--editor-version", version] if installed else ["install", version, "--resume"]
        if modules:
            args.extend(["--module", *modules, "--no-child-modules"])
        if eula:
            args.append("--accept-eula")
        return args

    def plan(self, version, modules, *, installed, eula, done, failed):
        """Ask the CLI what it would download (a dry run), without changing anything."""
        args = self.install_arguments(version, modules, installed=installed, eula=eula)
        self.run("install-plan", tr("install.planning"), args + ["--dry-run", "--yes"], done,
                 structured=True, failed=failed, timeout=CATALOG)

    def install(self, version, modules, *, installed, eula, done=None, failed=None):
        """One install at a time: a second one waits in the queue until the first is finished."""
        args = self.install_arguments(version, modules, installed=installed, eula=eula)
        self.run("install", tr("install.active", version), args + ["--yes"], done, failed=failed,
                 progress=True, queue=True)

    def module_list(self, version, done, failed):
        self.run("module-list", tr("install.step_modules"), ["install-modules", "--editor-version", version, "--list"],
                 lambda data: done(data["items"]), structured=True, failed=failed, timeout=CATALOG)

    def uninstall(self, version, done=None):
        self.run(f"uninstall:{version}", tr("editor.uninstalling", version), ["uninstall", version, "--yes"], done)

    def set_install_path(self, path, done=None):
        self.run("install-path", tr("editor.folder"), ["install-path", "--set", path], done, timeout=STATUS)

    # ---- projects and templates -----------------------------------------------------------------

    def templates(self, version, done, failed):
        self.run("templates:" + version, tr("template.browse"), ["templates", "--editor-version", version], done,
                 structured=True, failed=failed, timeout=CATALOG)

    def create_project(self, path, version, template, done=None):
        self.run(str(path), tr("new.create"), ["projects", "create", path.name, "--output-dir", str(path.parent),
                                               "--editor-version", version, "--template", template, "--no-cloud"],
                 done)

    def create_template(self, project, name):
        self.run(project, tr("template.create"), ["templates", "create", project, "--name", name])

    def cloud_status(self):
        self.run("cloud", tr("cloud.status"), ["cloud", "status"], timeout=CATALOG)

    def link_cloud(self, project, cloud):
        self.run(project, tr("cloud.link"), ["projects", "link", "cloud", project, "--cloud-project", cloud])

    # ---- packages of one project ----------------------------------------------------------------

    def project_command(self, project, title, args, done=None):
        self.run(project, title, [*args, "--project-path", project], done)

    def package_add(self, project, name, done=None):
        self.project_command(project, tr("package.install"), ["command", "package", "add", "--name", name,
                                                              "--confirm", "true", "--wait", "true", "--timeout", "300"],
                             done)

    def pipeline_install(self, project, done=None):
        self.project_command(project, tr("package.pipeline"), ["pipeline", "install"], done)

    def import_package(self, project, file, done=None):
        self.project_command(project, tr("package.import"), ["assets", "import", file], done)

    # ---- account and licenses -------------------------------------------------------------------

    def status(self, kind, done, failed):
        """Quiet read of `auth status` or `license status` (JSON data); kept out of the log and the top bar."""
        command = {"auth": ["auth", "status"], "license": ["license", "status"]}[kind]
        self.run(f"{kind}-status", tr("account.status"), command, done, structured=True, failed=failed, quiet=True,
                 timeout=STATUS)

    def account(self, title, args, after, timeout=ACCOUNT):
        """An account command; `after` runs whether it worked or not, so the shown state is re-read."""
        self.run("account", title, args, lambda _: after(), failed=lambda _: after(), timeout=timeout)

    def login(self, after):
        # Signing in waits for the browser: no time limit, the operation can be cancelled in the top bar.
        self.account(tr("account.login"), ["auth", "login"], after, timeout=0)

    def accounts(self, after):
        self.account(tr("account.accounts"), ["auth", "accounts"], after)

    def switch_account(self, account, after):
        self.account(tr("account.switch"), ["auth", "switch", account], after)

    def logout(self, after):
        self.account(tr("account.logout"), ["auth", "logout", "--yes"], after)

    def activate_personal(self, after):
        self.account(tr("license.personal"), ["license", "activate", "--personal", "--accept-eula"], after)

    def activate_file(self, path, after):
        self.account(tr("license.file"), ["license", "activate", "--file", path], after)
