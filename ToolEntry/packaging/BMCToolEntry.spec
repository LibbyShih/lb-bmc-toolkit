# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

_root     = os.path.dirname(SPECPATH)                            # ToolEntry/
_src      = os.path.join(_root, 'src')
_hub      = os.path.join(_src, 'hub')
_bmctool  = os.path.normpath(os.path.join(_root, '..'))          # siblings: CommandWebGUI, IPMI-inspector
_cwg_src  = os.path.join(_bmctool, 'CommandWebGUI',  'src')
_ipmi_src = os.path.join(_bmctool, 'IPMI-inspector', 'src')
_bmc_tpl  = os.path.join(_cwg_src, 'bmc_template')

# pyghmi uses os.listdir(__file__) to discover OEM plugins at runtime;
# collect_all() forces physical extraction to _MEIPASS so os.listdir() works.
_pyghmi_datas, _pyghmi_binaries, _pyghmi_hidden = collect_all('pyghmi')

a = Analysis(
    [os.path.join(_src, 'main.py')],
    pathex=[_src, _cwg_src, _ipmi_src],
    binaries=_pyghmi_binaries,
    datas=[
        (os.path.join(_cwg_src, 'blueprint.py'),              'cwg_src'),
        (os.path.join(_cwg_src, 'templates'),                 'cwg_src/templates'),
        (os.path.join(_cwg_src, 'static'),                    'cwg_src/static'),
        (os.path.join(_ipmi_src, 'blueprint.py'),             'ipmi_src'),
        (os.path.join(_ipmi_src, 'web', 'templates'),         'ipmi_src/web/templates'),
        (os.path.join(_ipmi_src, 'web', 'static'),            'ipmi_src/web/static'),
        (os.path.join(_hub, 'templates'),                     'hub/templates'),
        (os.path.join(_hub, 'static'),                        'hub/static'),
        (os.path.join(_bmc_tpl, 'templates'),                 'bmc_template/templates'),
        (os.path.join(_bmc_tpl, 'static'),                    'bmc_template/static'),
    ] + _pyghmi_datas,
    hiddenimports=[
        'pystray._win32', 'PIL._imagingtk',
        'yaml',
        'scapy', 'scapy.all', 'scapy.layers.all',
        'port_manager',
        'bmc_template', 'bmc_template.profile_api',
        'bmc_template.conn_format', 'bmc_template.connection_test',
        'decoders', 'decoders.sel', 'decoders.sdr', 'decoders.fru',
        'decoders.fru_multirecord', 'decoders.pcap', 'decoders.message',
        'spec', 'spec.netfn', 'spec.completion_codes', 'spec.sensor_types',
        'spec.sdr_types', 'spec.search_index', 'spec.oem_aspeed',
        'spec.dcmi', 'spec.node_manager', 'spec.request_schemas',
        'spec.response_schemas', 'spec.event_types',
        'spec.smbios_type38', 'spec.sps_me', 'spec.system_firmware',
        'transport', 'transport.rmcp',
        'storage', 'storage.db',
    ] + _pyghmi_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 'web' = IPMI inspector's standalone web/app.py; not needed in ToolEntry
    # and conflicts because bare 'blueprint' in PYZ resolves to CWG's version
    excludes=['web'],
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
    name='BMCToolEntry',
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
