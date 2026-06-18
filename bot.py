import os
import logging
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.deep_linking import create_start_link, decode_payload
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# .env faylini tizimga yuklash
load_dotenv()

# 1. BAZAVIY SOZLAMALAR (.env faylidan olinmoqda)
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# FSM - Javob berish jarayonini boshqarish holati
class BotStates(StatesGroup):
    waiting_for_reply = State()

# 2. MA'LUMOTLAR BAZASI BILAN ISHLASH
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # Hamkorlar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            clicks INTEGER DEFAULT 0
        )
    """)
    # Faol chatlar (kim kimga yozyapti) jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_chats (
            sender_id INTEGER PRIMARY KEY,
            receiver_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

# Bazani ishga tushirish
init_db()

def add_partner(user_id, name):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO partners (user_id, full_name) VALUES (?, ?)", (user_id, name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def is_partner(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM partners WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None or user_id == SUPER_ADMIN_ID

def increment_click(partner_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE partners SET clicks = clicks + 1 WHERE user_id = ?", (partner_id,))
    conn.commit()
    conn.close()

def get_stats(partner_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT clicks FROM partners WHERE user_id = ?", (partner_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else 0

def set_active_chat(sender_id, receiver_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO active_chats (sender_id, receiver_id) VALUES (?, ?)", (sender_id, receiver_id))
    conn.commit()
    conn.close()

def get_receiver_id(sender_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT receiver_id FROM active_chats WHERE sender_id = ?", (sender_id,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None


# 3. TUGMALAR (INLINE KEYBOARDS)
def get_partner_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Havolamni olish", callback_data="get_link")],
        [InlineKeyboardButton(text="📊 Havola Statistikasi", callback_data="get_stats")]
    ])
    return keyboard

def get_reply_keyboard(sender_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Javob yozish", callback_data=f"reply_to_{sender_id}")]
    ])
    return keyboard


# 4. /START BUYRUG'I
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = message.text.split()

    # Agar kimdir shaxsiy havola orqali kirsa
    if len(args) > 1:
        try:
            receiver_id = int(decode_payload(args[1]))
            if user_id == receiver_id:
                await message.answer("⚠️ Bu sizning shaxsiy havolangiz!")
                return
                
            set_active_chat(user_id, receiver_id)
            increment_click(receiver_id)  # Statistikani oshirish
            
            await message.answer(
                "🤫 **Anonim Chatga xush kelibsiz!**\n\n"
                "Bu yerga yozgan har qanday xabaringiz havola egasiga shaxsingiz yashirilgan holda yetkaziladi.\n"
                "Siz matn, rasm, video yoki audio yuborishingiz mumkin 👇"
            )
            return
        except Exception:
            await message.answer("❌ Havola eskirgan yoki noto'g'ri.")
            return

    # Agar hamkor yoki bosh admin bo'lsa
    if is_partner(user_id):
        role = "👑 Bosh Admin" if user_id == SUPER_ADMIN_ID else "🤝 Hamkor"
        text = (
            f"👋 Salom, {message.from_user.full_name}!\n"
            f"Siz botda **{role}** maqomidasiz.\n\n"
            f"Quyidagi tugmalardan birini tanlang:"
        )
        if user_id == SUPER_ADMIN_ID:
            text += "\n\n➕ Yangi foydalanuvchi qo'shish: `/add_user ID_RAQAM`"
            
        await message.answer(text, reply_markup=get_partner_keyboard(), parse_mode="Markdown")
    else:
        await message.answer("👋 Salom! Botdan foydalanish uchun sizda kimningdir shaxsiy havolasi bo'lishi kerak.")


# 5. TUGMA BOSILGANDA ISHLOVCHI QISM (CALLBACK HANDLERS)
@dp.callback_query(F.data == "get_link")
async def send_link_callback(callback: types.CallbackQuery):
    if is_partner(callback.from_user.id):
        link = await create_start_link(bot, str(callback.from_user.id), encode=True)
        await callback.message.answer(f"🔗 Mana sizning shaxsiy havolangiz:\n`{link}`\n\nUni profilingizga joylang!", parse_mode="Markdown")
        await callback.answer()

@dp.callback_query(F.data == "get_stats")
async def send_stats_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if is_partner(user_id):
        clicks = get_stats(user_id)
        await callback.message.answer(f"📊 **Sizning havolangiz statistikasi:**\n\n👥 Shaxsiy havolangizni jami **{clicks}** marta bosishgan.", parse_mode="Markdown")
        await callback.answer()

@dp.callback_query(F.data.startswith("reply_to_"))
async def setup_reply(callback: types.CallbackQuery, state: FSMContext):
    target_id = int(callback.data.split("_")[2])
    await state.update_data(reply_target=target_id)
    await state.set_state(BotStates.waiting_for_reply)
    
    await callback.message.answer("✍️ Javobingizni yozing yoki fayl yuboring, men uni anonim ravishda yetkazaman:")
    await callback.answer()


# 6. JAVOB YOZISH TIZIMI (FSM)
@dp.message(BotStates.waiting_for_reply)
async def send_reply_to_user(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    target_id = user_data.get("reply_target")
    
    try:
        await message.answer("⏳ Javob yuborilmoqda...")
        await bot.send_message(chat_id=target_id, text="🔔 **Siz yuborgan anonim xatga javob keldi:**")
        await message.copy_to(chat_id=target_id)
        await message.answer("✅ Javobingiz muvaffaqiyatli yetkazildi!")
    except Exception:
        await message.answer("❌ Xatni yetkazib bo'lmadi. Foydalanuvchi botni bloklagan bo'lishi mumkin.")
    
    await state.clear()


# 7. BOSH ADMIN UCHUN TANISH QO'SHISH BUYRUG'I
@dp.message(Command("add_user"), lambda message: message.from_user.id == SUPER_ADMIN_ID)
async def add_user_cmd(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Foydalanish: `/add_user 12345678`")
        return
    try:
        new_partner_id = int(args[1])
        success = add_partner(new_partner_id, "Tanish")
        if success:
            await message.answer(f"✅ ID: `{new_partner_id}` hamkor sifatida bazaga qo'shildi!", parse_mode="Markdown")
        else:
            await message.answer("❌ Bu foydalanuvchi allaqachon mavjud.")
    except ValueError:
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi shart.")


# 8. ANONIM XABARLARNI YOʻNALTIRISH (ENG ASOSIY QISM)
@dp.message()
async def forward_messages(message: types.Message):
    sender_id = message.from_user.id
    
    if is_partner(sender_id) and message.text and not message.text.startswith('/'):
        await message.answer("💡 Menyu tugmalaridan foydalaning yoki kelgan xabarlarga 'Javob yozish' tugmasi orqali javob bering.")
        return

    receiver_id = get_receiver_id(sender_id)
    if not receiver_id:
        await message.answer("❌ Siz hech kimning havola orqali kirmagansiz.")
        return

    username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    report_header = (
        f"📩 **Yangi anonim xabar!**\n"
        f"👤 **Kimdan:** {message.from_user.full_name}\n"
        f"🆔 **ID:** `{sender_id}`\n"
        f"🔗 **Username:** {username}\n"
        f"-------------------------\n"
        f"👇 Asl xabar:"
    )

    try:
        await bot.send_message(chat_id=receiver_id, text=report_header, parse_mode="Markdown")
        await message.copy_to(chat_id=receiver_id, reply_markup=get_reply_keyboard(sender_id))
        await message.answer("✅ Xabaringiz muvaffaqiyatli yetkazildi.")
    except Exception:
        await message.answer("❌ Xabar yuborishda xatolik yuz berdi.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
