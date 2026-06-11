# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

_root    = os.path.dirname(SPECPATH)   # IPMI-inspector/
_src     = os.path.join(_root, 'src')
_bmc_tpl = os.path.join(_src, 'bmc_template')

# pyghmi uses os.listdir(__file__) to discover OEM plugins at runtime;
# collect_all() forces physical extraction to _MEIPASS so os.listdir() works.
_pyghmi_datas, _pyghmi_binaries, _pyghmi_hidden = collect_all('pyghmi')

a = Analysis(
    [os.path.join(_src, 'main.py')],
    pathex=[_src],
    binaries=_pyghmi_binaries,
    datas=[
        (os.path.join(_src, 'web', 'templates'),      'web/templates'),
        (os.path.join(_src, 'web', 'static'),         'web/static'),
        (os.path.join(_bmc_tpl, 'templates'),          'bmc_template/templates'),
        (os.path.join(_bmc_tpl, 'static'),             'bmc_template/static'),
    ] + _pyghmi_datas,
    hiddenimports=[
        'pystray._win32', 'PIL._imagingtk',
        'yaml',
        'scapy', 'scapy.all', 'scapy.layers.all',
        'bmc_template', 'bmc_template.profile_api',
        'bmc_template.conn_format', 'bmc_template.connection_test',
    ] + _pyghmi_hidden,
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
    name='IPMIInspector',
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
