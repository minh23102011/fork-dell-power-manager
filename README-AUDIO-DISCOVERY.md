# PowerDeck PipeWire audio discovery

This bundle adds read-only audio discovery through WirePlumber's `wpctl`.

It reads:

- default sink volume;
- default sink mute state;
- default source volume;
- default source mute state;
- partial availability when only one default endpoint exists.

It uses:

```text
wpctl get-volume @DEFAULT_AUDIO_SINK@
wpctl get-volume @DEFAULT_AUDIO_SOURCE@
```

No audio state is changed.

## Install from ~/Projects

```fish
cd ~/Projects/PowerDeck
unzip -o ../powerdeck-audio-discovery.zip -d .
```

## Quality gate

```fish
source .venv/bin/activate.fish

python -m ruff check .
python -m mypy src
python -m pytest
python -m compileall -q src
```

Expected test count: 80 passed.

## Real-machine check

```fish
powerdeckctl status
powerdeckctl status --json
```

Expected result:

- an `Audio:` line with sink/source volume and mute state;
- `audio_control` is `true`;
- the `audio-control-unavailable` diagnostic disappears.
