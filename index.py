import os
import re
import asyncio
import requests
from flask import Flask, request
from Crypto.Cipher import AES
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- Configuration ---
TOKEN = '8183534977:AAGYLeHEUExoQTY3YNJ9yRp-NuVCSDOgXug'
VIDEO_FILE_ID = "BAACAgUAAxkBAAICYWmSDu9PxdumNL2jt_HuEbhU9ej8AAJUIAACnY2RVB4XvSbfaDVBOgQ"

app = Flask(__name__)
ptb_instance = Application.builder().token(TOKEN).build()

MODELS = ["DeepSeek-V1", "DeepSeek-R1", "DeepSeek-V3"]

class DeepSeekSession:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.model = "DeepSeek-R1"
        self.ready = False

    def bypass(self):
        try:
            r = self.session.get('https://asmodeus.free.nf/', timeout=5)
            nums = re.findall(r'toNumbers\("([a-f0-9]+)"\)', r.text)
            if len(nums) >= 3:
                key, iv, data = [bytes.fromhex(n) for n in nums[:3]]
                cookie = AES.new(key, AES.MODE_CBC, iv).decrypt(data).hex()
                self.session.cookies.set('__test', cookie, domain='asmodeus.free.nf')
                self.session.get('https://asmodeus.free.nf/index.php?i=1')
                self.ready = True
        except: pass

    def ask(self, q):
        if not self.ready: self.bypass()
        try:
            r = self.session.post('https://asmodeus.free.nf/deepseek.php', 
                                 params={'i': '1'}, 
                                 data={'model': self.model, 'question': q}, 
                                 timeout=25)
            res = re.search(r'class="response-content">(.*?)</div>', r.text, re.DOTALL)
            return re.sub(r'<[^>]*>', '', res.group(1)).strip() if res else "⚠️ Busy."
        except: return "❌ Timeout."

user_sessions = {}

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    user_sessions[uid] = DeepSeekSession()
    kb = [[InlineKeyboardButton(m, callback_data=f"s_{m}")] for m in MODELS]
    await u.message.reply_video(video=VIDEO_FILE_ID, caption="🤖 **DeepSeek Bot**", reply_markup=InlineKeyboardMarkup(kb))

async def msg_handler(u: Update, c: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    if uid not in user_sessions: user_sessions[uid] = DeepSeekSession()
    wait_msg = await u.message.reply_text("⏳ Thinking...")
    ans = await asyncio.to_thread(user_sessions[uid].ask, u.message.text)
    await c.bot.edit_message_text(chat_id=uid, message_id=wait_msg.message_id, text=ans)

ptb_instance.add_handler(CommandHandler("start", start))
ptb_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))

@app.route('/', methods=['POST', 'GET'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), ptb_instance.bot)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ptb_instance.initialize())
        loop.run_until_complete(ptb_instance.process_update(update))
        return "OK", 200
    return "Bot is running on Render!", 200

