# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for KherveSlide on macOS.
#
#   .venv/bin/pip install pyinstaller
#   .venv/bin/pyinstaller KherveSlideMAC.spec --noconfirm
#     -> dist/KherveSlide.app
#
# Builds for the Mac it runs on (Apple Silicon or Intel). PyInstaller signs
# the bundle ad hoc, which Apple Silicon needs to run it at all; it is not
# notarised, so on another Mac the first launch is right-click > Open.
#
# Finder lists KherveSlide for .kslide presentations and PowerPoint files.
#
# The Windows build is KherveSlide.spec; both share packaging/spec_common.py.
#
# Copyright (C) 2026 Gwilherm Kerherve.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH) / "packaging"))
import spec_common as common  # noqa: E402

FULL_VERSION, SHORT_VERSION = common.stamp_version()
_ICO, ICNS = common.icons()
datas, binaries, hiddenimports = common.analysis_inputs()
print(f"Building {common.APP_NAME} v{FULL_VERSION} for macOS")

a = Analysis(
    [common.ENTRY],
    pathex=[str(common.ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=common.EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KherveSlide",
    icon=ICNS,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,       # files arrive as QFileOpenEvent instead
    target_arch=None,           # the build Mac's own architecture
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KherveSlide",
)

app = BUNDLE(
    coll,
    name="KherveSlide.app",
    icon=ICNS,
    bundle_identifier="com.kerherve.kherveslide",
    # CFBundleShortVersionString must be dot-separated digits: no '+sha'.
    version=SHORT_VERSION,
    info_plist={
        "CFBundleName": "KherveSlide",
        "CFBundleDisplayName": "KherveSlide",
        "CFBundleShortVersionString": SHORT_VERSION,
        "CFBundleVersion": SHORT_VERSION,
        "CFBundleGetInfoString": f"KherveSlide {FULL_VERSION}",
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,          # sharp text on Retina
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright":
            "Copyright (C) 2026 Gwilherm Kerherve",
        "UTExportedTypeDeclarations": [{
            "UTTypeIdentifier": "com.kerherve.kherveslide.presentation",
            "UTTypeDescription": "KherveSlide presentation",
            "UTTypeConformsTo": ["public.json", "public.data"],
            "UTTypeTagSpecification": {"public.filename-extension": ["kslide"]},
        }],
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "KherveSlide presentation",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["com.kerherve.kherveslide.presentation"],
                "CFBundleTypeExtensions": ["kslide"],
            },
            {
                # Imported, not owned: PowerPoint keeps .pptx.
                "CFBundleTypeName": "PowerPoint presentation",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "CFBundleTypeExtensions": ["pptx"],
            },
        ],
    },
)
