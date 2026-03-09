import os, glob, json, shutil

history_dir = os.path.expandvars(r"%APPDATA%\Code\User\History")
target_files = {
    "api_client.py": "api",
    "main_window.py": "ui",
    "server.py": "server",
    "tab_admin.py": "ui",
    "tab_autobidder.py": "ui",
    "tab_creative.py": "ui",
    "tab_dashboard.py": "ui",
    "tab_extension.py": "ui",
    "tab_guide.py": "ui",
    "tab_keyword.py": "ui",
    "tab_settings.py": "ui"
}

found = {}
for entry_file in glob.glob(os.path.join(history_dir, "*", "entries.json")):
    try:
        with open(entry_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            res = data.get("resource", "")
            if "py_naver" in res and "naver_search_auto" in res:
                for tf, dest_folder in target_files.items():
                    if res.endswith("/" + tf) or res.endswith("%5C" + tf):
                        # get the newest entry
                        entries = data.get("entries", [])
                        if entries:
                            latest_id = entries[-1]["id"]
                            source_path = os.path.join(os.path.dirname(entry_file), latest_id)
                            
                            # check if size > 1000 to avoid empty file
                            if os.path.exists(source_path) and os.path.getsize(source_path) > 1000:
                                # We might have multiple workspaces. So let's keep the largest or latest.
                                if tf not in found or os.path.getmtime(source_path) > os.path.getmtime(found[tf]):
                                    found[tf] = source_path
    except Exception as e:
        pass

for tf, src in found.items():
    dest_dir = target_files[tf]
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    dest_path = os.path.join(dest_dir, tf)
    
    print(f"Restoring {tf} from {src} (Size: {os.path.getsize(src)})")
    shutil.copy2(src, dest_path)
    
    # We will modify the import path just like we intended in Python.
    with open(dest_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if dest_dir == "ui":
        content = content.replace("from api_client import api", "from api.api_client import api")
        if tf == "main_window.py":
            old_imports = [
                "from tab_autobidder import AutoBidderWidget",
                "from tab_creative import CreativeManagerWidget",
                "from tab_extension import ExtensionManagerWidget",
                "from tab_keyword import KeywordExpanderWidget",
                "from tab_admin import AdminDashboardWidget",
                "from tab_settings import SettingsWidget",
                "from tab_guide import UserGuideWidget",
                "from tab_dashboard import DashboardWidget"
            ]
            for im in old_imports:
                content = content.replace(im, im.replace("from tab_", "from ui.tab_"))
            
            if "sys.path.append" not in content:
                content = content.replace("import sys\n", "import sys\nimport os\nsys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
    
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Done restoring files.")
