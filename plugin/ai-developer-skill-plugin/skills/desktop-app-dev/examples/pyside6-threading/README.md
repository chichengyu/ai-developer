# PySide6 Threading Demo

Install PySide6 and run:

```powershell
pip install PySide6
python examples/pyside6-threading/app.py
```

## Package

PySide6 apps are typically distributed with PyInstaller:

```powershell
powershell -File scripts/build_python.ps1 `
  -Entry examples/pyside6-threading/app.py `
  -Name PySide6Demo `
  -HiddenImports PySide6.QtCore,PySide6.QtWidgets,PySide6.QtGui
```
