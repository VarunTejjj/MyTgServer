#!/usr/bin/env python3
"""
Telegram bot — Updated: do NOT delete primary storage content nor messages with channel join inline buttons.

Behavior:
- Option A base: delete content flows after 5 minutes for non-admins.
- EXCEPTIONS:
    * primary storage (storage.json) delivered via GET LEAKS is NOT auto-deleted.
    * messages containing channel join inline buttons (join_markup and want_more_markup) are NOT auto-deleted.
- storage1 (full access) and collections still auto-delete (media + notices) after 5 minutes.
- Welcome image is NOT auto-deleted (per your choice).

Drop-in replacement: save as bot.py and run with python.
"""

import os
import re
import json
import time
import random
import threading
import traceback
import telebot
from datetime import datetime, timedelta, timezone
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaAnimation,
    InputMediaVideo,
)

broadcast_data = {
    "active": False,
    "type": None,
    "text": None,
    "file_id": None,
    "caption": None
}

# ---------------- CONFIG ----------------
BOT_TOKEN = "8427278708:AAEb2s8Avdrb-Na-XPTT99Nl3GegX8141zc"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ===== JOIN CONTROL =====
REQUIRE_JOIN = True   # 🔒 joining required again

# ================== JOIN CHECK (2 CHANNELS ONLY) ==================

CHANNEL_1 = -1003675426104
CHANNEL_1_LINK = "https://t.me/+8ZOt2DIRcRszMGY1"

CHANNEL_2 = -1003674032744   # your updates channel
CHANNEL_2_LINK = "https://t.me/bestleaksfrrr"

ALERT_CHANNEL_ID = -1003330581399


def is_joined(user_id, channel_id):
    try:
        member = bot.get_chat_member(channel_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        print(f"[is_joined error] user={user_id} channel={channel_id} err={e}")
        return False


def is_joined_both(user_id):
    """
    Returns True only if user joined BOTH channels.
    """
    return is_joined(user_id, CHANNEL_1) and is_joined(user_id, CHANNEL_2)


def join_markup():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔥 JOIN MAIN CHANNEL 🔥", url=CHANNEL_1_LINK))
    kb.add(InlineKeyboardButton("📢 JOIN UPDATES CHANNEL 📢", url=CHANNEL_2_LINK))
    kb.add(InlineKeyboardButton("✅ I JOINED", callback_data="check_join"))
    return kb

# Admin chat id (exempt)
ADMIN_CHAT_ID = 1831313735
ADMIN_HELP = "t.me/MadMax31c"

# Storage files (persistent JSON)
STORAGE_META = "storage.json"         # primary leaks (do NOT auto-delete)
STORAGE1_META = "storage1.json"       # full-access leaks (auto-deleted)
COLLECTIONS_META = "collections.json" # mapping collection_key -> list of items

# =============== USERS SYSTEM ===============

REQUIRE_JOIN = False   # 🔴 TEMPORARY: allow content without joining

USERS_META = "users.json"

def load_users():
    if os.path.exists(USERS_META):
        try:
            with open(USERS_META, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_users(data):
    with open(USERS_META, "w") as f:
        json.dump(data, f, indent=2)

# All known users stored in a file
users = load_users()

def add_user(uid):
    if uid not in users:
        users.append(uid)
        save_users(users)
        
def notify_new_user(user):
    user_id = user.id
    first = user.first_name or ""
    last = user.last_name or ""
    name = (first + " " + last).strip()
    username = f"@{user.username}" if user.username else "No username"

    text = (
        "🚨 *New Bot Start*\n\n"
        f"👤 Name: {name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"🔗 Username: {username}"
    )

    try:
        bot.send_message(
            ALERT_CHANNEL_ID,
            text,
            parse_mode="Markdown"
        )
        print(f"[ALERT SENT] User {user_id}")

    except Exception as e:
        print(f"[ALERT ERROR] {e}")

# Auto-delete delay (seconds)
AUTO_DELETE_DELAY = None  # 5 minutes

# Welcome image (not auto-deleted)
WELCOME_IMAGES = [
    "https://i.ibb.co/6JF8fpf9/IMG-20251216-014823-325.jpg",
    "https://i.ibb.co/7Jk347Ph/IMG-20251214-215704-244.jpg",
    "https://i.ibb.co/jv6q7qcC/IMG-20251216-014841-946.jpg",
    "https://i.ibb.co/tMvT3Q6S/IMG-20251216-223436-855.jpg",
    "https://i.ibb.co/6fPnbMD/IMG-20251216-223558-752.jpg",
    "https://i.ibb.co/B5f66QGJ/IMG-20251216-225423-419.jpg",
    "https://i.ibb.co/zpWjVrX/IMG-20251216-225804.jpg",    
]

WELCOME_ROTATE_SECONDS = 300  # 5 minutes


# ---------------- STATE ----------------
admin_state = {"awaiting_items": False, "temp_items": []}    # for /storage
admin_state1 = {"awaiting_items": False, "temp_items": []}   # for /storage1
admin_newstate = {"awaiting_items": False, "temp_items": []} # for /newstorage

# ---------------- IO helpers ----------------
def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[load_json] failed to read {path}: {e}")
            return None
    return None

def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[save_json] saved {path} (entries={len(data) if isinstance(data,(list,dict)) else 'N/A'})")
    except Exception as e:
        print(f"[save_json] failed to write {path}: {e}")
        raise

stored_items = load_json(STORAGE_META)
if not isinstance(stored_items, list):
    stored_items = []

stored_items1 = load_json(STORAGE1_META)
if not isinstance(stored_items1, list):
    stored_items1 = []

collections = load_json(COLLECTIONS_META)
if not isinstance(collections, dict):
    collections = {}

# ---------------- UTIL ----------------
def normalize_entry(e):
    if isinstance(e, str):
        return {"type": "photo", "file_id": e}
    if isinstance(e, dict) and "file_id" in e and "type" in e:
        if e["type"] in ("photo", "animation", "video"):
            return e
    return None

def is_joined(user_id, channel_id):
    try:
        member = bot.get_chat_member(channel_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

def is_joined_both(user_id):
    return (
        is_joined(user_id, CHANNEL_1) and
        is_joined(user_id, CHANNEL_2)
    )

def is_joined_all(user_id):
    if not REQUIRE_JOIN:
        return True
    try:
        return (
            is_joined(user_id, CHANNEL_1) and
            is_joined(user_id, CHANNEL_2)
        )
    except Exception:
        return False

# Backwards-compatible alias (optional) — remove if you don't want the old name
def is_joined_both(user_id):
    """Legacy: returns True if user joined CHANNEL_1 and CHANNEL_2."""
    return is_joined(user_id, CHANNEL_1) and is_joined(user_id, CHANNEL_2)

def should_protect(chat_id):
    return chat_id != ADMIN_CHAT_ID

def get_bot_username():
    try:
        me = bot.get_me()
        return getattr(me, "username", None)
    except Exception as e:
        print(f"[get_bot_username] error: {e}")
        return None

# ---------------- MARKUPS ----------------
def join_markup():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔥 Join Leaks Channel", url=CHANNEL_1_LINK))
    kb.add(InlineKeyboardButton("📢 Join Updates Channel", url=CHANNEL_2_LINK))
    kb.add(InlineKeyboardButton("✅ I Joined", callback_data="check_join"))
    return kb

def leaks_markup():
    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton("🔥 Check Muskan Karia Leaks", callback_data="get_leaks"))
    return mk

def leaks_markup():
    mk = InlineKeyboardMarkup()    
    mk.add(InlineKeyboardButton("Check MORE FREE PREMIUM LEAKS 🤩", url=CHANNEL_1_LINK))
    mk.add(InlineKeyboardButton("CONTACT ADMIN NEED HELP 👤", url=NEED_HELP))
    return mk

def want_more_markup():
    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton("📢 Join Channel 3", url=CHANNEL_3_LINK))
    mk.add(InlineKeyboardButton("✔️ I Joined 3", callback_data="check_join3"))
    return mk

def get_current_welcome_image_ist():
    """
    Returns a welcome image based on Indian time (IST),
    changing every 5 minutes.
    """
    if not WELCOME_IMAGES:
        return None

    # IST timezone (UTC +5:30)
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)

    # total minutes passed today in IST
    total_minutes = now_ist.hour * 60 + now_ist.minute

    # each slot = 5 minutes
    slot = total_minutes // 5

    # rotate through images
    index = slot % len(WELCOME_IMAGES)
    return WELCOME_IMAGES[index]

# ---------------- SEND ITEMS (return records) ----------------
def send_items_and_return_records(chat_id, items, caption_prefix=None):
    protect = should_protect(chat_id)
    records = []
    norm = []
    for e in items:
        ne = normalize_entry(e)
        if ne:
            norm.append(ne)

    i = 0
    n = len(norm)
    while i < n:
        kind = norm[i]["type"]
        if kind == "photo":
            photos = []
            j = i
            while j < n and norm[j]["type"] == "photo" and len(photos) < 10:
                photos.append(norm[j]["file_id"])
                j += 1
            if len(photos) == 1:
                try:
                    msg = bot.send_photo(chat_id, photos[0], caption=caption_prefix or None, protect_content=protect)
                    if hasattr(msg, "message_id"):
                        records.append({"message_id": msg.message_id, "type": "photo"})
                except Exception as e:
                    print(f"[send_items] send_photo error: {e}")
            else:
                media = []
                for fid in photos:
                    media.append(InputMediaPhoto(media=fid))
                try:
                    msgs = bot.send_media_group(chat_id, media, protect_content=protect)
                    if isinstance(msgs, list):
                        for m in msgs:
                            if hasattr(m, "message_id"):
                                records.append({"message_id": m.message_id, "type": "photo"})
                    else:
                        if hasattr(msgs, "message_id"):
                            records.append({"message_id": msgs.message_id, "type": "photo"})
                except Exception as e:
                    print(f"[send_items] send_media_group photos error: {e}")
            i = j
        elif kind == "animation":
            try:
                msg = bot.send_animation(chat_id, norm[i]["file_id"], caption=(caption_prefix if i == 0 else None), protect_content=protect)
                if hasattr(msg, "message_id"):
                    records.append({"message_id": msg.message_id, "type": "animation"})
            except Exception as e:
                print(f"[send_items] send_animation error: {e}")
            i += 1
        elif kind == "video":
            try:
                msg = bot.send_video(chat_id, norm[i]["file_id"], caption=(caption_prefix if i == 0 else None), protect_content=protect)
                if hasattr(msg, "message_id"):
                    records.append({"message_id": msg.message_id, "type": "video"})
            except Exception as e:
                print(f"[send_items] send_video error: {e}")
            i += 1
        else:
            print(f"[send_items] unknown type skipped: {kind}")
            i += 1

    print(f"[send_items] sent {len(records)} messages to chat {chat_id}")
    return records

# ---------------- START PAYLOAD PARSER ----------------
def parse_start_payload(raw_text: str):
    if not raw_text:
        return None
    txt = raw_text.strip()
    txt = re.sub(r'^\/*\s*start', '', txt, flags=re.IGNORECASE).strip()
    if not txt:
        return None
    m = re.fullmatch(r'(\d+)', txt)
    if m:
        return f"collection_{m.group(1)}"
    m = re.fullmatch(r'collection[_]?(\d+)', txt, flags=re.IGNORECASE)
    if m:
        return f"collection_{m.group(1)}"
    m = re.search(r'collection.*?(\d+)', txt, flags=re.IGNORECASE)
    if m:
        return f"collection_{m.group(1)}"
    return None

# ---------------- COMMAND HANDLERS ----------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    # ---------- BASIC SETUP ----------
    chat_id = message.chat.id
    protect = should_protect(chat_id)

    # ---------- SAVE USER ----------
    try:
        add_user(chat_id)
    except Exception as e:
        print("[add_user error]", e)

    # ---------- ALERT CHANNEL ----------
    try:
        notify_new_user(message.from_user)
    except Exception as e:
        print("[notify_new_user error]", e)

    text = message.text or ""
    key = parse_start_payload(text)

    # ---------------- DEEP-LINK COLLECTION (JOIN REQUIRED) ----------------
    if key:
        user_id = message.from_user.id

        if not is_joined_both(user_id):
            bot.send_message(
                chat_id,
                "⚠️ *You must join both channels to access this content.*\n\n"
                "Join both channels below and click *I Joined*.",
                parse_mode="Markdown",
                reply_markup=join_markup(),
                protect_content=protect
            )
            return

        coll = collections.get(key)
        if not coll:
            bot.send_message(
                chat_id,
                f"⚠️ Collection *{key}* not found or expired.",
                parse_mode="Markdown",
                protect_content=protect
            )
            return

        records = send_items_and_return_records(
            chat_id,
            coll,
            caption_prefix="🔥 Here is your requested collection"
        )

        notice_id = None
        try:
            notice = bot.send_message(
                chat_id,
                "Iteams Will Be Not Cleared From Chat ✅ Enjoy Watching 🙌🏻",
                protect_content=protect
            )
            notice_id = notice.message_id
        except:
            pass

        if chat_id != ADMIN_CHAT_ID and records:
            ids = [r["message_id"] for r in records]
            if notice_id:
                ids.append(notice_id)
            schedule_delete_messages(chat_id, ids, delay=AUTO_DELETE_DELAY)

        bot.send_message(chat_id, "📌 Enjoy Watching", protect_content=protect)
        return

    # ---------------- NORMAL START FLOW ----------------
    user = message.from_user
    fn = user.first_name or ""
    ln = user.last_name or ""
    uname = user.username or ""
    display_name = (fn + (" " + ln if ln else "")).strip() or uname or "there"

    def escape_md(t: str):
        return re.sub(r'([_*\[\]\(\)~`>#+\-=|{}.!])', r'\\\1', t)

    safe_name = escape_md(display_name)
    caption = f"🎉 Welcome, *{safe_name}*!"

    # ---------- WELCOME IMAGE (ROTATING EVERY 5 MINUTES) ----------
    try:
        welcome_image = get_current_welcome_image_ist()

        if welcome_image:
            if welcome_image.lower().startswith("http"):
                bot.send_photo(
                    chat_id,
                    welcome_image,
                    caption=caption,
                    parse_mode="Markdown",
                    protect_content=protect
                )
            elif os.path.exists(welcome_image):
                with open(welcome_image, "rb") as f:
                    bot.send_photo(
                        chat_id,
                        f,
                        caption=caption,
                        parse_mode="Markdown",
                        protect_content=protect
                    )
            else:
                bot.send_message(chat_id, caption, parse_mode="Markdown", protect_content=protect)
        else:
            bot.send_message(chat_id, caption, parse_mode="Markdown", protect_content=protect)

    except Exception as e:
        print("[WELCOME_IMAGE ERROR]", e)
        bot.send_message(chat_id, caption, parse_mode="Markdown", protect_content=protect)

    # ---------------- NEW CHANNEL NOTICE ----------------
    notice_text = (
        "🚨 *Important Update*\n\n"
        "Our *old channel was banned* ❌\n\n"
        "👉 Join our *NEW OFFICIAL CHANNELS* below to stay updated.\n"
        "All future content & updates will be posted there."
    )

    notice_kb = InlineKeyboardMarkup()
    notice_kb.add(
        InlineKeyboardButton("🔥 JOIN LEAKS CHANNEL 🔥", url=CHANNEL_1_LINK)
    )
    notice_kb.add(
        InlineKeyboardButton("📢 JOIN UPDATES CHANNEL 📢", url=CHANNEL_2_LINK)
    )

    try:
        notice_msg = bot.send_message(
            chat_id,
            notice_text,
            parse_mode="Markdown",
            reply_markup=notice_kb,
            disable_web_page_preview=True,
            protect_content=protect
        )

        # delete notice after 60 seconds
        schedule_delete_messages(chat_id, [notice_msg.message_id], delay=60)

    except Exception as e:
        print("[notice error]", e)


# ---------- /storage (admin) ----------
@bot.message_handler(commands=['storage'])
def cmd_storage(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ You are not authorized.", protect_content=should_protect(message.chat.id))
        return
    admin_state["awaiting_items"] = True
    admin_state["temp_items"] = []
    bot.send_message(message.chat.id, "📥 Send photos/GIFs/videos for /storage. When finished send /done", protect_content=False)

@bot.message_handler(commands=['done'])
def cmd_done(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ You are not authorized.", protect_content=should_protect(message.chat.id))
        return
    if not admin_state.get("awaiting_items", False):
        bot.send_message(message.chat.id, "ℹ️ No active /storage session. Use /storage to start.", protect_content=False)
        return
    if admin_state["temp_items"]:
        stored_items.extend(admin_state["temp_items"])
        try:
            save_json(STORAGE_META, stored_items)
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Failed to save storage.json: {e}", protect_content=False)
            return
        cnt = len(admin_state["temp_items"])
        admin_state["temp_items"] = []
        admin_state["awaiting_items"] = False
        bot.send_message(message.chat.id, f"✅ Saved {cnt} item(s) to storage.json. Total now {len(stored_items)}", protect_content=False)
    else:
        admin_state["awaiting_items"] = False
        bot.send_message(message.chat.id, "⚠️ No items were uploaded. Session canceled.", protect_content=False)

# ---------- /storage1 (admin) ----------
@bot.message_handler(commands=['storage1'])
def cmd_storage1(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    admin_state1["awaiting_items"] = True
    admin_state1["temp_items"] = []
    bot.send_message(message.chat.id, "📥 Send photos/GIFs/videos for /storage1. When finished send /done1", protect_content=False)

@bot.message_handler(commands=['done1'])
def cmd_done1(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    if not admin_state1.get("awaiting_items", False):
        bot.send_message(message.chat.id, "ℹ️ No active /storage1 session. Use /storage1 to start.", protect_content=False)
        return
    if admin_state1["temp_items"]:
        stored_items1.extend(admin_state1["temp_items"])
        try:
            save_json(STORAGE1_META, stored_items1)
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠️ Failed to save storage1.json: {e}", protect_content=False)
            return
        cnt = len(admin_state1["temp_items"])
        admin_state1["temp_items"] = []
        admin_state1["awaiting_items"] = False
        bot.send_message(message.chat.id, f"✅ Saved {cnt} item(s) to storage1.json. Total now {len(stored_items1)}", protect_content=False)
    else:
        admin_state1["awaiting_items"] = False
        bot.send_message(message.chat.id, "⚠️ No items were uploaded. Session canceled.", protect_content=False)

# ---------- /newstorage & /donestorage (admin) ----------
@bot.message_handler(commands=['newstorage'])
def cmd_newstorage(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    admin_newstate["awaiting_items"] = True
    admin_newstate["temp_items"] = []
    bot.send_message(message.chat.id, "📥 Send photos/GIFs/videos for this new collection. When finished send /donestorage", protect_content=False)

@bot.message_handler(commands=['donestorage'])
def cmd_donestorage(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    if not admin_newstate.get("awaiting_items", False):
        bot.send_message(message.chat.id, "ℹ️ No active /newstorage session. Use /newstorage to start.", protect_content=False)
        return
    items = admin_newstate.get("temp_items", [])
    if not items:
        admin_newstate["awaiting_items"] = False
        admin_newstate["temp_items"] = []
        bot.send_message(message.chat.id, "⚠️ No items uploaded. Session canceled.", protect_content=False)
        return

    key = f"collection_{int(time.time())}"
    collections[key] = items.copy()
    try:
        save_json(COLLECTIONS_META, collections)
    except Exception as e_save:
        bot.send_message(message.chat.id, f"⚠️ Failed to save collection: {e_save}", protect_content=False)
        return

    admin_newstate["temp_items"] = []
    admin_newstate["awaiting_items"] = False

    bot_username = get_bot_username()
    if bot_username:
        start_link = f"https://t.me/{bot_username}?start={key}"
    else:
        start_link = f"/start {key}"
    resp = (
        f"✅ Created collection *{key}* and saved {len(collections[key])} item(s).\n\n"
        f"Share this link to deliver it to users:\n{start_link}\n\n"
        "Note: if the link is `/start <key>` copy it and share as `https://t.me/<your_bot_username>?start=<key>` once you have the username."
    )
    bot.send_message(message.chat.id, resp, parse_mode="Markdown", protect_content=False)
    print(f"[donestorage] Created {key} with {len(collections[key])} items")

# ---------------- MEDIA HANDLER (admin-only) ----------------
@bot.message_handler(content_types=['photo','animation','video'])
def handle_media(message):
    try:
        # /storage flow (primary storage) - these items will NOT be auto-deleted when delivered via Get Leaks
        if message.from_user.id == ADMIN_CHAT_ID and admin_state.get("awaiting_items", False):
            if message.content_type == "photo":
                fid = message.photo[-1].file_id
                admin_state["temp_items"].append({"type":"photo","file_id":fid})
            elif message.content_type == "animation":
                fid = message.animation.file_id
                admin_state["temp_items"].append({"type":"animation","file_id":fid})
            elif message.content_type == "video":
                fid = message.video.file_id
                admin_state["temp_items"].append({"type":"video","file_id":fid})
            bot.send_message(message.chat.id, f"🟢 Recorded for /storage ({len(admin_state['temp_items'])}). Send /done when finished.", protect_content=False)
            return

        # /storage1 flow (full access) - these items WILL be auto-deleted
        if message.from_user.id == ADMIN_CHAT_ID and admin_state1.get("awaiting_items", False):
            if message.content_type == "photo":
                fid = message.photo[-1].file_id
                admin_state1["temp_items"].append({"type":"photo","file_id":fid})
            elif message.content_type == "animation":
                fid = message.animation.file_id
                admin_state1["temp_items"].append({"type":"animation","file_id":fid})
            elif message.content_type == "video":
                fid = message.video.file_id
                admin_state1["temp_items"].append({"type":"video","file_id":fid})
            bot.send_message(message.chat.id, f"🟢 Recorded for /storage1 ({len(admin_state1['temp_items'])}). Send /done1 when finished.", protect_content=False)
            return

        # /newstorage flow (collections) - these items WILL be auto-deleted when delivered
        if message.from_user.id == ADMIN_CHAT_ID and admin_newstate.get("awaiting_items", False):
            if message.content_type == "photo":
                fid = message.photo[-1].file_id
                admin_newstate["temp_items"].append({"type":"photo","file_id":fid})
            elif message.content_type == "animation":
                fid = message.animation.file_id
                admin_newstate["temp_items"].append({"type":"animation","file_id":fid})
            elif message.content_type == "video":
                fid = message.video.file_id
                admin_newstate["temp_items"].append({"type":"video","file_id":fid})
            bot.send_message(message.chat.id, f"🟢 Recorded for collection ({len(admin_newstate['temp_items'])}). Send /donestorage when finished.", protect_content=False)
            return
    except Exception as e:
        print(f"[handle_media] exception: {e}")
        traceback.print_exc()
        try:
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ Error recording media: {e}", protect_content=False)
        except:
            pass
    # ignore uploads from non-admins

# ---------------- CALLBACKS ----------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    # save user
    try:
        add_user(call.message.chat.id)
    except:
        pass

    data = call.data
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    protect = should_protect(chat_id)

    # ---------------- CHECK JOIN ----------------
    if data == "check_join":
        if not is_joined_both(user_id):
            try:
                bot.edit_message_text(
                    "❌ *You must join BOTH channels to continue.*\n\n"
                    "Join both channels and click *I Joined* again.",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=join_markup(),
                    parse_mode="Markdown"
                )
            except:
                bot.send_message(
                    chat_id,
                    "❌ You must join BOTH channels to continue.",
                    reply_markup=join_markup(),
                    protect_content=protect
                )

            bot.answer_callback_query(call.id)
            return

        # ✅ USER JOINED BOTH CHANNELS

        # remove join buttons & say thanks
        try:
            bot.edit_message_text(
                "✅ *Thanks for joining!* 🎉\n\n"
                "Watch the video below to understand how to use the bot.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode="Markdown"
            )
        except:
            pass

        # send tutorial video / animation
        for item in stored_items:
            if isinstance(item, dict) and item.get("type") in ("video", "animation"):
                try:
                    if item["type"] == "video":
                        bot.send_video(
                            chat_id,
                            item["file_id"],
                            caption="🔥 We have the best premium leaks for FREE 🤗 Go Back To Channel @bestleaksfrrrr Click On Any Link And Watch 👍🏻",
                            protect_content=protect
                        )
                    else:
                        bot.send_animation(
                            chat_id,
                            item["file_id"],
                            caption="🔥 We have the best premium leaks for FREE 🤗 Go Back To Channel @bestleaksfrrrr Click On Any Link And Watch 👍🏻",
                            protect_content=protect
                        )
                except Exception as e:
                    print("[tutorial send error]", e)
                break

        # FINAL BUTTONS (OPEN CHANNEL + CONTACT ADMIN)
        final_kb = InlineKeyboardMarkup()
        final_kb.add(
            InlineKeyboardButton("🔥 OPEN LEAKS CHANNEL 🔥", url=CHANNEL_1_LINK)
        )
        final_kb.add(
            InlineKeyboardButton("📩 CONTACT ADMIN", url=f"https://t.me/{ADMIN_USERNAME}")
        )

        bot.send_message(
            chat_id,
            "👇 Click below to continue:",
            reply_markup=final_kb,
            protect_content=protect
        )

        bot.answer_callback_query(call.id)
        return

# ---------------- ADMIN UTILITIES ----------------
@bot.message_handler(commands=['list_storage'])
def cmd_list_storage(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    if not stored_items:
        bot.send_message(message.chat.id, "No stored items in storage.json", protect_content=False)
        return
    text = "storage.json items (up to 50):\n" + "\n".join(f"{i+1}. {it.get('type') if isinstance(it,dict) else 'photo'} | {it.get('file_id') if isinstance(it,dict) else it}" for i,it in enumerate(stored_items[:50]))
    bot.send_message(message.chat.id, text, protect_content=False)

@bot.message_handler(commands=['list_storage1'])
def cmd_list_storage1(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    if not stored_items1:
        bot.send_message(message.chat.id, "No stored items in storage1.json", protect_content=False)
        return
    text = "storage1.json items (up to 50):\n" + "\n".join(f"{i+1}. {it.get('type') if isinstance(it,dict) else 'photo'} | {it.get('file_id') if isinstance(it,dict) else it}" for i,it in enumerate(stored_items1[:50]))
    bot.send_message(message.chat.id, text, protect_content=False)

@bot.message_handler(commands=['list_collections'])
def cmd_list_collections(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    if not collections:
        bot.send_message(message.chat.id, "No collections created yet.", protect_content=False)
        return
    text = "Collections:\n" + "\n".join(f"{k} (items={len(v)})" for k,v in collections.items())
    bot.send_message(message.chat.id, text, protect_content=False)

@bot.message_handler(commands=['clear_storage'])
def cmd_clear_storage(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    stored_items.clear()
    save_json(STORAGE_META, stored_items)
    bot.send_message(message.chat.id, "✅ Cleared storage.json", protect_content=False)

@bot.message_handler(commands=['clear_storage1'])
def cmd_clear_storage1(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    stored_items1.clear()
    save_json(STORAGE1_META, stored_items1)
    bot.send_message(message.chat.id, "✅ Cleared storage1.json", protect_content=False)

@bot.message_handler(commands=['delete_collection'])
def cmd_delete_collection(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /delete_collection <collection_key>", protect_content=False)
        return
    key = parts[1].strip()
    if key in collections:
        del collections[key]
        save_json(COLLECTIONS_META, collections)
        bot.send_message(message.chat.id, f"✅ Deleted collection {key}", protect_content=False)
    else:
        bot.send_message(message.chat.id, "Collection not found.", protect_content=False)

# ---------------- TEST AUTODELETE (admin) ----------------
@bot.message_handler(commands=['test_autodelete'])
def cmd_test_autodelete(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ Not authorized.", protect_content=should_protect(message.chat.id))
        return
    try:
        sent = bot.send_message(message.chat.id, "Test autodelete (10s). This will be removed shortly.", protect_content=False)
        mid = sent.message_id if hasattr(sent, "message_id") else None
        if mid:
            schedule_delete_messages(message.chat.id, [mid], delay=10)
            bot.send_message(message.chat.id, "Scheduled test message for deletion in 10s.", protect_content=False)
        else:
            bot.send_message(message.chat.id, "Failed to schedule test delete: could not get message id.", protect_content=False)
    except Exception as e:
        bot.send_message(message.chat.id, f"Test failed: {e}", protect_content=False)

@bot.message_handler(commands=['recover_users'])
def recover_users(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return bot.send_message(message.chat.id, "❌ Not authorized.")

    try:
        with open("users.json", "r") as f:
            users_list = json.load(f)
    except Exception as e:
        return bot.send_message(message.chat.id, f"❌ Failed to read users.json: {e}")

    if not isinstance(users_list, list) or not users_list:
        return bot.send_message(message.chat.id, "⚠️ users.json is empty or invalid.")

    sent = 0
    failed = 0

    bot.send_message(message.chat.id, f"🚀 Sending new channel invite to {len(users_list)} users...")

    for uid in users_list:
        try:
            bot.send_message(
                int(uid),
                f"🚨 *Important Update*\n\n"
                f"Our old channel was banned.\n\n"
                f"👉 Join our *NEW OFFICIAL CHANNEL* below:\n"
                f"{NEW_CHANNEL_LINK}\n\n"
                f"⚠️ Join now to continue receiving content.",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            sent += 1
        except Exception as e:
            failed += 1
            print(f"[recover_users] Failed for {uid}: {e}")

    bot.send_message(
        message.chat.id,
        f"✅ Recovery finished!\n\n"
        f"📨 Sent: {sent}\n"
        f"❌ Failed (blocked/deleted): {failed}"
    )

@bot.message_handler(commands=['broadcast'])
def broadcast_now(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    # must reply to a message
    if not message.reply_to_message:
        bot.send_message(
            message.chat.id,
            "❌ Please reply to a *text* or *photo* message with /broadcast",
            parse_mode="Markdown"
        )
        return

    # load users
    try:
        with open("users.json", "r") as f:
            users_list = json.load(f)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Failed to read users.json: {e}")
        return

    sent = 0
    failed = 0

    bot.send_message(
        message.chat.id,
        f"🚀 Broadcasting to {len(users_list)} users..."
    )

    src = message.reply_to_message

    for uid in users_list:
        try:
            uid = int(uid)

            # TEXT broadcast
            if src.content_type == "text":
                bot.send_message(uid, src.text)

            # PHOTO + caption broadcast
            elif src.content_type == "photo":
                bot.send_photo(
                    uid,
                    src.photo[-1].file_id,
                    caption=src.caption or ""
                )

            else:
                continue

            sent += 1

        except Exception as e:
            failed += 1
            print(f"[broadcast failed] {uid}: {e}")

    bot.send_message(
        message.chat.id,
        f"✅ Broadcast finished\n\n"
        f"📨 Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )
    
@bot.message_handler(content_types=['text'])
def capture_broadcast_text(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    if not broadcast_data["active"]:
        return
    if message.text.startswith("/"):
        return
    if not message.reply_to_message:
        return

    broadcast_data["type"] = "text"
    broadcast_data["text"] = message.text

    bot.send_message(message.chat.id, "✅ Broadcast text saved")
    
@bot.message_handler(content_types=['photo'])
def capture_broadcast_photo(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    if not broadcast_data["active"]:
        return
    if not message.reply_to_message:
        return

    broadcast_data["type"] = "photo"
    broadcast_data["file_id"] = message.photo[-1].file_id
    broadcast_data["caption"] = message.caption or ""

    bot.send_message(message.chat.id, "✅ Broadcast image saved") 

@bot.message_handler(commands=['sendbroadcast'])
def send_broadcast(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    if not broadcast_data["active"]:
        return bot.send_message(message.chat.id, "❌ No active broadcast.")

    try:
        with open("users.json", "r") as f:
            users_list = json.load(f)
    except Exception as e:
        return bot.send_message(message.chat.id, f"❌ Failed to read users.json: {e}")

    sent = 0
    failed = 0

    bot.send_message(message.chat.id, f"🚀 Sending broadcast to {len(users_list)} users...")

    for uid in users_list:
        try:
            uid = int(uid)

            if broadcast_data["type"] == "text":
                bot.send_message(uid, broadcast_data["text"])

            elif broadcast_data["type"] == "photo":
                bot.send_photo(
                    uid,
                    broadcast_data["file_id"],
                    caption=broadcast_data["caption"]
                )

            sent += 1

        except Exception as e:
            failed += 1
            print(f"[broadcast failed] {uid}: {e}")

    broadcast_data["active"] = False

    bot.send_message(
        message.chat.id,
        f"✅ Broadcast finished\n\n"
        f"📨 Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )

# ---------------- START POLLING ----------------
if __name__ == "__main__":
    print("Bot running — Option A with exceptions: storage content preserved and channel-join messages preserved.")
    bot.infinity_polling()