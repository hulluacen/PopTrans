from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


ROOT = Path(SPECPATH).parent

binaries = collect_dynamic_libs("llama_cpp")
datas = collect_data_files(
    "rapidocr_onnxruntime",
    includes=["config.yaml"],
)
datas += copy_metadata("python-multipart")

hiddenimports = collect_submodules("uvicorn")
hiddenimports += collect_submodules("rapidocr_onnxruntime")
hiddenimports += [
    "multipart",
    "python_multipart",
    "python_multipart.multipart",
]

a = Analysis(
    [str(ROOT / "backend" / "api_server.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jupyter",
        "matplotlib",
        "onnxruntime.quantization",
        "onnxruntime.tools",
        "tkinter",
    ],
    noarchive=False,
    optimize=1,
)

# Dependency scanning also places llama.cpp DLLs at the bundle root. Keep
# the identical copy beside llama.dll, where its loader resolves dependencies.
# CUDA libraries are large, so duplicate copies substantially slow extraction.
llama_sources = {
    str(Path(source).resolve()).casefold()
    for target, source, kind in a.binaries
    if target.replace("\\", "/").startswith("llama_cpp/lib/")
}
a.binaries = [
    entry for entry in a.binaries
    if "/" in entry[0].replace("\\", "/")
    or str(Path(entry[1]).resolve()).casefold() not in llama_sources
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ai_engine",
    version=str(ROOT / "backend" / "version_info.txt"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "assets" / "icon.ico")],
)
