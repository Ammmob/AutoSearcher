from pathlib import Path

import selenium

project_root = Path(SPECPATH).parent
source_root = project_root / "src"
selenium_root = Path(selenium.__file__).resolve().parent
selenium_manager = (
    selenium_root
    / "webdriver"
    / "common"
    / "windows"
    / "selenium-manager.exe"
)
selenium_javascript = [
    (
        str(path),
        "selenium/webdriver/remote",
    )
    for path in sorted((selenium_root / "webdriver" / "remote").glob("*.js"))
]

analysis = Analysis(
    [str(source_root / "auto_searcher" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=[
        (
            str(selenium_manager),
            "selenium/webdriver/common/windows",
        )
    ],
    datas=selenium_javascript,
    hiddenimports=["selenium.webdriver.common.action_chains"],
    hookspath=[str(project_root / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=1,
)

python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AutoSearcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AutoSearcher",
)
