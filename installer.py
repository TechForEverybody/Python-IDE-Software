import PyInstaller.__main__
import os 


handling_files = []

for root, subdirectories, files in os.walk("./thonny/plugins"):
    for filename in files :
        if os.path.join(root, filename).find("__pycache__") == -1:
            filepath = os.path.join(root, filename)
        new_root = root.replace("\\", "/")
    if root.find("__pycache__") == -1:
        print(new_root)
        handling_files.append(f"""--add-data={new_root[2:]}/*:{new_root[2:]}/""")

print(handling_files)

PyInstaller.__main__.run([
    'index.py',
    '--windowed',
    # '--onefile',
    "--icon",
    "innovator.ico",
    "--add-data=thonny/res/*:thonny/res/",
    "--add-data=thonny/plugins/*:thonny/plugins/",
    "--add-data=thonny/plugins/cpython_frontend/*:thonny/plugins/cpython_frontend/",
    "--add-data=thonny/plugins/cpython_backend/*:thonny/plugins/cpython_backend/",
    "--hidden-import=thonny",

]+handling_files)