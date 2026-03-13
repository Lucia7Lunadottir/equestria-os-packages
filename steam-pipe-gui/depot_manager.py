import os
import tempfile

class DepotManager:
    @staticmethod
    def create_simple_vdf(app_id: str, desc: str, content_root: str, branch: str, set_live: bool) -> str:
        depot_id = str(int(app_id) + 1) if app_id.isdigit() else "0"

        vdf = f""""AppBuild"
{{
\t"AppID"\t\t"{app_id}"
\t"Desc"\t\t"{desc.replace('"', '\\"')}"
\t"ContentRoot"\t"{content_root}"
"""
        if set_live and branch:
            vdf += f'\t"SetLive"\t"{branch}"\n'

        vdf += f"""\t"Depots"
\t{{
\t\t"{depot_id}"
\t\t{{
\t\t\t"FileMapping"
\t\t\t{{
\t\t\t\t"LocalPath"\t"*"
\t\t\t\t"DepotPath"\t"."
\t\t\t\t"recursive"\t"1"
\t\t\t}}
\t\t}}
\t}}
}}"""
        vdf_dir = os.path.join(tempfile.gettempdir(), "SteamPipeGUI")
        os.makedirs(vdf_dir, exist_ok=True)
        vdf_path = os.path.join(vdf_dir, f"app_{app_id}_build.vdf")

        with open(vdf_path, 'w', encoding='utf-8') as f:
            f.write(vdf)

        return vdf_path
