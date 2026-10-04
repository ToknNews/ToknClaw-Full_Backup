"""Explicit setup mode changes; validate and replace the complete non-secret config."""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import tempfile

from .config import load_config


def set_mode(path, mode):
    if mode not in {'off', 'shadow', 'live'}:
        raise ValueError('unsupported setup mode')
    path = Path(path)
    if path.is_symlink():
        raise ValueError('configuration must be a regular file, not a symlink')
    original = path.read_bytes()
    config = load_config(path)
    updated = replace(config, setup_enabled=mode != 'off', setup_publish=mode == 'live')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup = path.with_name(path.name + '.before-setup-' + stamp)
    with backup.open('xb') as handle:
        handle.write(original)
    backup.chmod(stat.S_IMODE(path.stat().st_mode))
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(asdict(updated), handle, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'mode': mode, 'configuration': str(path), 'backup': str(backup),
            'applies_to': 'new setups; existing shadow watches are never replayed into the feed'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/market_watch.json')
    parser.add_argument('--mode', choices=['off', 'shadow', 'live'], required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(set_mode(args.config, args.mode), indent=2))
    except (ValueError, OSError):
        parser.exit(1, 'Could not update the configuration; check its path and validated settings.\n')


if __name__ == '__main__':
    main()
