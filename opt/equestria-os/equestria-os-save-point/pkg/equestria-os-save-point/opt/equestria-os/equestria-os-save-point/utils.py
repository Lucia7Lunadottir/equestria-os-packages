import subprocess

def launch_terminal(bash_cmd: str):
    for term, args in [
        ("konsole",        ["konsole", "-e"]),
        ("xfce4-terminal", ["xfce4-terminal", "--hold", "-e"]),
        ("xterm",          ["xterm", "-hold", "-e"]),
    ]:
        try:
            subprocess.run(["which", term], capture_output=True, check=True)
            subprocess.Popen(args + ["bash", "-c", bash_cmd])
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    subprocess.Popen(["bash", "-c", bash_cmd])