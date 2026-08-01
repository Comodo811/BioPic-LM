# Private Stacking Methods

BioPic can ship public builds without exposing private stacking methods, while
still allowing private users to copy method files into a known folder later.

Private methods are exposed when BioPic can find their implementation files:

- `Custom`
- `Custom2`

## Keep Methods Local But Out Of Git

For local development, keep the files in the normal method folder:

```text
src/biopic/imaging/stacking/methods/custom.py
src/biopic/imaging/stacking/methods/custom2.py
```

Those exact files are ignored by `.gitignore`, so they can stay in your working
tree without being included by `git add .` in a public source release.

## Drop-In Folder For Distributed Builds

For a packaged app, users can add private methods after installation by creating
this folder next to the executable:

```text
BioPic LM/
  BioPic LM.exe
  private_methods/
    custom.py
    custom2.py
```

On the next app start, BioPic detects those files and shows the corresponding
stacking methods. If only `custom.py` exists, only `Custom` is shown. If only
`custom2.py` exists, only `Custom2` is shown.

Each file must expose the expected entry point:

```text
custom.py   -> stack_custom(images, parameters, progress=None, preview=None)
custom2.py  -> stack_custom2(images, parameters, progress=None, preview=None)
```

For source runs, BioPic also searches:

```text
private_methods/
```

in the current working directory. Advanced users can point to another folder:

```powershell
$env:BIOPIC_PRIVATE_STACKING_PATH = "D:\MyPrivateBioPicMethods"
```

## Private Packaged Build

If you want the methods already bundled inside a private build, restore the
private source files before packaging:

```powershell
python -m PyInstaller BioPicLM.spec --clean --noconfirm
```

If you want to force the private section to be considered enabled for debugging,
you can still set:

```powershell
$env:BIOPIC_ENABLE_PRIVATE_STACKING = "1"
```

but normal use does not require this variable. File discovery is enough.
