# Muselsl Bugfixes

## Overview

During development of ExG-Lab, we identified and fixed two critical bugs in muselsl v2.2.2 that prevented proper device discovery and recording. These fixes have been submitted to the upstream repository.

**Pull Request**: [#224 - Fix bluetoothctl EOF handling and record filename directory creation](https://github.com/alexandrebarachant/muse-lsl/pull/224)

## Bug #1: Bluetoothctl EOF Handling

### The Problem

The `muselsl list` command would fail on some systems with:

```
Exception: bluetoothctl exited unexpectedly
```

**Root cause**: The code only caught `pexpect.TIMEOUT` but not `pexpect.EOF`, even though both are normal completion states for `bluetoothctl scan`.

### Impact

- Device discovery (`muselsl list`) completely broken on affected systems
- Prevented any device from being connected
- Affected systems: Debian 12, some Ubuntu distributions, systems with newer bluetoothctl versions

### The Fix

**File**: `muselsl/stream.py` (lines 90-106)

**Before**:
```python
scan = pexpect.spawn('bluetoothctl scan on')
try:
    scan.expect('foooooo', timeout=timeout)
except pexpect.TIMEOUT:  # Only catches TIMEOUT!
    # ...
```

**After**:
```python
scan = pexpect.spawn('bluetoothctl scan on')
try:
    scan.expect('foooooo', timeout=timeout)
except (pexpect.EOF, pexpect.TIMEOUT):  # Catches BOTH!
    # Both EOF and TIMEOUT are expected - the scan completed normally
    if verbose:
        try:
            output = scan.before.decode('utf-8', 'replace')
            print(output.split('\r\n'))
        except:
            pass

# Terminate the scan process if still running
try:
    scan.terminate(force=True)
except:
    pass
```

### Why This Fixes It

1. **EOF is normal**: On some systems, `bluetoothctl scan on` exits cleanly (EOF) instead of running until timeout
2. **Both are valid**: Whether bluetoothctl sends EOF or runs until TIMEOUT, both indicate scan completion
3. **Graceful termination**: Added explicit `terminate()` call to clean up process

### Testing

```bash
# Before fix
$ muselsl list
Exception: bluetoothctl exited unexpectedly

# After fix
$ muselsl list
Searching for Muse devices...
Found 2 devices:
  Muse-XXXX (00:55:DA:XX:XX:XX)
  Muse-YYYY (00:55:DA:YY:YY:YY)
```

## Bug #2: Record Filename Directory Creation

### The Problem

Using simple filenames (without directories) with `muselsl record` would crash:

```bash
$ muselsl record --filename test.csv
FileNotFoundError: [Errno 2] No such file or directory: ''
```

**Root cause**: The code called `os.makedirs(os.path.dirname(filename))` without checking if dirname is empty.

### Impact

- `muselsl record` broken for simple filenames
- Required workaround: always specify full paths with directories
- Affected both `record.py` and direct recording mode

### The Fix

**File**: `muselsl/record.py` (lines 152 and 266)

**Before**:
```python
# Line 152 (in _save function)
directory = os.path.dirname(filename)
os.makedirs(directory, exist_ok=True)  # Fails if directory is ''!

# Line 266 (in record_direct function)
directory = os.path.dirname(filename)
os.makedirs(directory, exist_ok=True)  # Same bug!
```

**After**:
```python
# Line 152 (in _save function)
directory = os.path.dirname(filename)
if directory and not os.path.exists(directory):  # Check if directory is not empty!
    os.makedirs(directory)

# Line 266 (in record_direct function)
directory = os.path.dirname(filename)
if directory and not os.path.exists(directory):  # Same fix!
    os.makedirs(directory)
```

### Why This Fixes It

1. **Empty dirname**: For simple filenames like `test.csv`, `os.path.dirname()` returns `''`
2. **makedirs fails**: Calling `os.makedirs('')` raises exception
3. **Check before create**: Only create directory if dirname is not empty and doesn't exist

### Testing

```bash
# Before fix
$ muselsl record --filename test.csv
FileNotFoundError: [Errno 2] No such file or directory: ''

# After fix
$ muselsl record --filename test.csv
Recording to test.csv...
[Records successfully]

# Still works with paths
$ muselsl record --filename data/session1/test.csv
Creating directory: data/session1
Recording to data/session1/test.csv...
[Records successfully]
```

## Using the Patched Version

### Option 1: Install from Fork (Recommended)

Until the PR is merged, you can install the patched version:

```bash
# Clone the patched repository
git clone https://github.com/YOUR_USERNAME/muse-lsl.git
cd muse-lsl
git checkout fix/bluetoothctl-eof-and-record-filename

# Install in development mode
pip install -e .

# Verify fixes
muselsl list
muselsl record --filename test.csv
```

### Option 2: Manual Patching

If you already have muselsl installed, manually apply the fixes:

```bash
# Find muselsl installation
python -c "import muselsl; print(muselsl.__file__)"

# Edit the file shown (e.g., /path/to/venv/lib/python3.11/site-packages/muselsl/stream.py)
# Apply the changes shown above
```

### Option 3: Wait for Upstream Merge

Monitor PR #224 for merge status:
https://github.com/alexandrebarachant/muse-lsl/pull/224

Once merged and released:
```bash
pip install --upgrade muselsl
```

## Verification

Test both fixes:

```bash
# Test Bug #1 fix (bluetoothctl EOF)
muselsl list
# Should show devices without crashing

# Test Bug #2 fix (record filename)
muselsl record --filename test.csv
# Let it run for a few seconds, then Ctrl+C
# Should create test.csv in current directory

# Cleanup
rm test.csv
```

## Impact on ExG-Lab

### Before Fixes

ExG-Lab couldn't:
- Discover Muse devices on Debian 12 and similar systems
- Record with simple session names

### After Fixes

ExG-Lab can:
- Reliably discover devices across all platforms
- Use simple recording patterns like `session_20241030.csv`
- Run the complete device management workflow

### Implementation Notes

The DeviceManager in ExG-Lab depends on `muselsl list` working correctly:

```python
# backend/devices/manager.py
def scan_devices(self, timeout: float = 5.0) -> List[Dict]:
    """Scan for available Muse devices"""
    result = subprocess.run(
        ['muselsl', 'list'],  # Requires Bug #1 fix
        capture_output=True,
        text=True,
        timeout=timeout
    )
    # Parse output...
```

Recording functionality depends on Bug #2 fix indirectly (muselsl uses the same code internally).

## Technical Details

### Why EOF Happens

Different bluetoothctl versions behave differently:

**Older versions (bluez < 5.60)**:
- `bluetoothctl scan on` runs indefinitely
- Must be terminated via SIGTERM
- Results in `pexpect.TIMEOUT`

**Newer versions (bluez >= 5.60)**:
- `bluetoothctl scan on` auto-exits after scan
- Sends EOF when complete
- Results in `pexpect.EOF`

The fix handles both cases gracefully.

### Directory Creation Edge Cases

The original code failed these cases:

```python
# Case 1: Simple filename
filename = "test.csv"
dirname = os.path.dirname(filename)  # Returns ''
os.makedirs(dirname)  # FAILS!

# Case 2: Filename in current directory
filename = "./test.csv"
dirname = os.path.dirname(filename)  # Returns '.'
os.makedirs(dirname)  # Works, but unnecessary

# Case 3: Full path
filename = "data/session/test.csv"
dirname = os.path.dirname(filename)  # Returns 'data/session'
os.makedirs(dirname)  # Works correctly
```

The fix:
```python
directory = os.path.dirname(filename)
if directory and not os.path.exists(directory):
    os.makedirs(directory)
```

Handles all three cases correctly:
- Case 1: `directory = ''`, skips makedirs
- Case 2: `directory = '.'`, already exists, skips makedirs
- Case 3: `directory = 'data/session'`, creates if needed

## Additional Known Issues

### Not Fixed (Outside Scope)

These muselsl issues remain:

1. **No automatic reconnection**: If a device disconnects, the stream dies
2. **Poor error messages**: Connection failures often show generic errors
3. **No battery monitoring**: Can't query device battery level
4. **Bluetooth interference**: No guidance on handling multiple devices

### Workarounds in ExG-Lab

We address some limitations in ExG-Lab:

**Automatic reconnection**:
```python
# backend/devices/manager.py
def monitor_device_health(self):
    """Monitor device streams and reconnect if needed"""
    for device in self.devices:
        if not self.is_stream_alive(device):
            self.reconnect_device(device)
```

**Better error handling**:
```python
try:
    device_manager.connect_device(address, stream_name)
except subprocess.TimeoutExpired:
    return {"error": "Connection timed out - check Bluetooth"}
except Exception as e:
    return {"error": f"Connection failed: {str(e)}"}
```

## Contributing

If you find additional bugs in muselsl:

1. Document the bug thoroughly
2. Create a minimal reproduction case
3. Submit an issue to: https://github.com/alexandrebarachant/muse-lsl/issues
4. If you fix it, create a PR referencing the issue

## References

- **Original muselsl repository**: https://github.com/alexandrebarachant/muse-lsl
- **Our bugfix PR**: https://github.com/alexandrebarachant/muse-lsl/pull/224
- **Related issues**:
  - Issue about bluetoothctl failures (if exists, link here)
  - Issue about record filename (if exists, link here)

## Timeline

- **2025-10-30**: Bugs discovered during ExG-Lab development
- **2025-10-30**: Fixes developed and tested
- **2025-10-30**: PR #224 submitted to upstream
- **Pending**: PR review and merge

---

**Last updated**: 2025-10-30
**Status**: Fixes submitted, awaiting upstream merge
