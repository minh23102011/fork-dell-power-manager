"""Flat, low-overdraw GTK theme for the PowerDeck standalone app."""

from __future__ import annotations

POWERDECK_CSS = r"""
window,
.powerdeck-root {
    background: #101415;
    color: #e9eeee;
}

headerbar {
    background: #14191a;
    border-bottom: 1px solid #2a3031;
    min-height: 54px;
}

headerbar .title {
    color: #f1f5f5;
    font-weight: 700;
}

.powerdeck-brand {
    color: #f1f5f5;
    font-size: 16px;
    font-weight: 750;
}

.powerdeck-sidebar {
    background: #151a1b;
    border-right: 1px solid #2a3031;
    padding: 14px 10px;
}

.powerdeck-nav {
    background: transparent;
    border: 0;
    border-radius: 8px;
    color: #b8c0c0;
    min-height: 46px;
    padding: 0 12px;
}

.powerdeck-nav:hover {
    background: #1d2324;
    color: #eef2f2;
}

.powerdeck-nav:checked {
    background: #242b2c;
    color: #f4f7f7;
    border-left: 3px solid #67b9c4;
}

.powerdeck-nav label {
    font-weight: 600;
}

.powerdeck-status-chip {
    background: #1d2324;
    border: 1px solid #2c3334;
    border-radius: 8px;
    color: #c7cece;
    padding: 5px 9px;
}

.powerdeck-page {
    padding: 26px 28px 36px 28px;
}

.powerdeck-page-title {
    color: #f2f5f5;
    font-size: 26px;
    font-weight: 750;
}

.powerdeck-page-description {
    color: #8f9999;
    font-size: 14px;
}

.powerdeck-section-title {
    color: #e4e9e9;
    font-size: 14px;
    font-weight: 700;
}

.powerdeck-card {
    background: #1b2021;
    border: 1px solid #2b3132;
    border-radius: 11px;
}

.powerdeck-card-row {
    min-height: 56px;
    padding: 8px 12px;
}

.powerdeck-card-row-tall {
    min-height: 68px;
}

.powerdeck-row-title {
    color: #e3e8e8;
    font-size: 14px;
    font-weight: 500;
}

.powerdeck-row-subtitle {
    color: #879191;
    font-size: 11px;
}

.powerdeck-value {
    color: #9ba5a5;
    font-size: 14px;
}

.powerdeck-separator {
    background: #2a3031;
    min-height: 1px;
}

.powerdeck-quiet-box {
    background: #181d1e;
    border: 1px solid #293031;
    border-radius: 10px;
    padding: 10px 12px;
}

.powerdeck-quiet-text {
    color: #8f9999;
    font-size: 12px;
}

.powerdeck-badge {
    background: #2a3031;
    border-radius: 7px;
    color: #b8c0c0;
    padding: 4px 8px;
}

button.suggested-action {
    background: #78c7d0;
    color: #12383c;
    border: 0;
    border-radius: 8px;
    font-weight: 700;
    min-height: 36px;
    padding: 0 14px;
}

button.suggested-action:hover {
    background: #8ed2da;
}

button.suggested-action:disabled {
    background: #394546;
    color: #7b8585;
}

dropdown,
spinbutton {
    background: #252b2c;
    border: 1px solid #303738;
    border-radius: 8px;
    color: #e4e8e8;
    min-height: 36px;
}

switch {
    min-width: 40px;
}

scrollbar slider {
    min-width: 7px;
    min-height: 32px;
    background: #454c4d;
    border-radius: 7px;
}

scrollbar trough {
    background: transparent;
}

.powerdeck-two-column {
    margin-top: 2px;
}
"""


__all__ = ["POWERDECK_CSS"]
