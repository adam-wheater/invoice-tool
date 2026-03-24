# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['invoice.py'],
    pathex=[],
    binaries=[],
    datas=[('template.html', '.')],
    hiddenimports=[
        'reportlab.graphics.barcode.code128',
        'reportlab.graphics.barcode.code93',
        'reportlab.graphics.barcode.code39',
        'reportlab.graphics.barcode.usps',
        'reportlab.graphics.barcode.usps4s',
        'reportlab.graphics.barcode.qr',
        'reportlab.graphics.barcode.ecc200datamatrix',
        'reportlab.graphics.barcode.widgets',
        'reportlab.graphics.barcode.common',
        'reportlab.graphics.barcode.eanbc',
        'reportlab.graphics.barcode.lto',
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
    name='invoice',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
