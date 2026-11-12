"""End-to-end identity OTP route tests on an isolated PostgreSQL schema."""
import os
import unittest
import time
import uuid
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
from cryptography.fernet import Fernet

import app as application
import identity_lookup
import identity_auth_core


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "0002_identity_core.sql",
    ROOT / "migrations" / "0005_otp_request_limits.sql",
    ROOT / "migrations" / "0006_session_authentication_freshness.sql",
    ROOT / "migrations" / "0009_identity_otp_hardening.sql",
    ROOT / "migrations" / "0010_otp_signup_policy_versions.sql",
    ROOT / "migrations" / "0011_otp_email_transactional_outbox.sql",
    ROOT / "migrations" / "0013_otp_delivery_uncertainty.sql",
)
