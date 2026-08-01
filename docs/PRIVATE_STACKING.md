# Private Stacking Methods

BioPic can ship public builds without exposing private stacking methods.

By default, private methods are disabled:

- `Custom`
- `Custom2`

Enable them only for a local/private build:

```powershell
$env:BIOPIC_ENABLE_PRIVATE_STACKING = "1"
python -m biopic.app.main
```

For a packaged private build:

```powershell
$env:BIOPIC_ENABLE_PRIVATE_STACKING = "1"
python -m PyInstaller BioPicLM.spec --clean --noconfirm
```

Do not commit proprietary implementations to the public source branch. Keep
private method modules in one of the ignored locations:

- `src/biopic_private/`
- `private_plugins/`

The public branch should either remove the implementation files entirely or
keep only non-proprietary stubs that raise a clear "private method disabled"
error.

If you build without private methods, you can add them later by restoring the
private source files from a private branch or local ignored folder and setting
`BIOPIC_ENABLE_PRIVATE_STACKING=1` before running or packaging.

The public tree keeps only lazy loader hooks for private methods. A private
build must restore compatible implementations at:

- `src/biopic/imaging/stacking/methods/custom.py`
- `src/biopic/imaging/stacking/methods/custom2.py`

Without those files, enabling `BIOPIC_ENABLE_PRIVATE_STACKING` intentionally
shows a clear "module is not installed" error instead of silently falling back
to another stacker.
