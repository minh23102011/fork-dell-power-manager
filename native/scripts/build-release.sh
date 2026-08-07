#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

require() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf '%s\n' "missing required command: $1" >&2
        exit 1
    fi
}

require cargo
require cmake
require ninja
require c++

printf '%s\n' '==> Building Rust workspace (release)'
cargo build --manifest-path "$ROOT/Cargo.toml" --release --workspace

printf '%s\n' '==> Configuring Qt6 GUI'
cmake \
    -S "$ROOT/qt" \
    -B "$ROOT/qt/build" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release

printf '%s\n' '==> Building Qt6 GUI'
cmake --build "$ROOT/qt/build" --parallel

printf '%s\n' '==> Native release build complete'
printf '%s\n' "Rust binaries: $ROOT/target/release"
printf '%s\n' "Qt binary:      $ROOT/qt/build/powerdeck-native"
