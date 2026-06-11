# -*- mode: python ; coding: utf-8 -*-
import os

_root    = os.path.dirname(SPECPATH)   # CommandWebGUI/
_src     = os.path.join(_root, 'src')
_bmc_tpl = os.path.join(_src, 'bmc_template')

a = Analysis(
    [os.path.join(_src, 'main.py')],
    pathex=[_src],
    binaries=[],
    datas=[
        (os.path.join(_src, 'templates'),      'templates'),
        (os.path.join(_src, 'static'),         'static'),
        (os.path.join(_bmc_tpl, 'templates'),  'bmc_template/templates'),
        (os.path.join(_bmc_tpl, 'static'),     'bmc_template/static'),
    ],
    hiddenimports=[
        'pystray._win32', 'PIL._imagingtk',
        'port_manager',
        'bmc_template', 'bmc_template.profile_api',
        'bmc_template.conn_format', 'bmc_template.connection_test',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CommandWebGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
