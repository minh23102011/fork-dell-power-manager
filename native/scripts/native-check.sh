#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT=$(CDPATH= cd -- "$ROOT/.." && pwd)

printf '%s\n' '==> Rust format'
cargo fmt --manifest-path "$ROOT/Cargo.toml" --all -- --check

printf '%s\n' '==> Rust Clippy'
cargo clippy \
    --manifest-path "$ROOT/Cargo.toml" \
    --workspace \
    --all-targets \
    -- \
    -D warnings

printf '%s\n' '==> Rust tests'
cargo test --manifest-path "$ROOT/Cargo.toml" --workspace

printf '%s\n' '==> Rust release'
cargo build --manifest-path "$ROOT/Cargo.toml" --release --workspace

printf '%s\n' '==> Qt configure/build'
cmake \
    -S "$ROOT/qt" \
    -B "$ROOT/qt/build" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release
cmake --build "$ROOT/qt/build" --parallel

if find "$PROJECT" \
    -path "$PROJECT/.git" -prune -o \
    -path "$PROJECT/.venv" -prune -o \
    -path "$ROOT/target" -prune -o \
    -path "$ROOT/qt/build" -prune -o \
    -name '*.py' -print \
    | grep -q .; then
    printf '%s\n' 'tracked/source Python files still exist in the checkout' >&2
    exit 1
fi

if [ -f "$PROJECT/pyproject.toml" ]; then
    printf '%s\n' 'pyproject.toml still exists after native cutover' >&2
    exit 1
fi

printf '%s\n' '==> Full native quality gate passed'
