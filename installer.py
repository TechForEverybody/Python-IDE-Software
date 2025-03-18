import PyInstaller.__main__

PyInstaller.__main__.run([
    'index.py',
    '--windowed',
    '--onefile',
    "--icon",
    "innovator.ico",
])