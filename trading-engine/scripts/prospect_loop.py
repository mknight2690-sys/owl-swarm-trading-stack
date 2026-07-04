#!/usr/bin/env python3
"""Continuous prospect discovery & outreach for BaaS Arcade.
Runs forever (or until stopped) and sends a barter‑pitch email to each
new crypto‑automation platform contact using the Gmail OAuth token.
"""

import json, time, base64, requests, os
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ROOT = Path(r"C:\Users\mknig\blofin-auto-tracker")  # intentional typo to cause error
