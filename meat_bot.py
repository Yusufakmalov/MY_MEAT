import logging
import os
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.error import BadRequest

if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv()

# Constants from .env
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
CREATOR_ID = int(os.getenv("CREATOR_ID", "0"))


DATABASE_URL = os.getenv("DATABASE_URL")

def db_connect():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Certificate photo file paths
CERTIFICATE_IMAGES = {
    "cert_sanitary": "certificates/cert_sanitary.png",
    "cert_veterinary": "certificates/veterenar_cert.png",
    "cert_halal": "certificates/halal_cert.png"
}


# --- Utility Functions ---
async def check_subscription(user_id, context):
    if CREATOR_ID and int(user_id) == CREATOR_ID:
        logger.info(f"User {user_id} is the creator. Bypassing subscription check.")
        return True
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Subscription check error for user {user_id}: {e}")
        return False



def get_all_meats():
    conn = db_connect()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT code, name, price, image, amount FROM meat
            ''')
            return cur.fetchall()
    finally:
        conn.close()

def add_user_if_not_exists(user, is_subscribed):
    conn = db_connect()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO users (tg_id, first_name, last_name, username, is_subscribed)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tg_id) DO NOTHING
            ''', (user.id, user.first_name, user.last_name, user.username, is_subscribed))
            conn.commit()
    finally:
        conn.close()

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Sertifikatlar', callback_data='halal_cert_evidence'),
         InlineKeyboardButton('Video', callback_data='show_video')],
        [InlineKeyboardButton('Biz haqimizda', callback_data='about'),
         InlineKeyboardButton('Kontaktlar', callback_data='contacts')],
        [InlineKeyboardButton('Goshtlar', callback_data='meats')]
    ])

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    is_subscribed = await check_subscription(user_id, context)
    add_user_if_not_exists(user, is_subscribed)

    if is_subscribed:
        welcome_text = (
            "\U0001F44B <b>Go‘sht Tashkiloti Botiga xush kelibsiz!</b>\n\n"
            "Bu yerda siz quyidagilarni qilishingiz mumkin:\n"
            "✅ Halol sertifikatlarni ko‘rish\n"
            "✅ Go‘shtni qayta ishlash bo‘yicha videolarni tomosha qilish\n"
            "✅ Go‘sht turlarini ko‘rib chiqish\n"
            "✅ Biz haqimizda ma’lumot olish va kontaktlarni ko‘rish\n\n"
            "Quyidagi menyudan tanlang:"
        )
        await update.message.reply_text(
            welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode='HTML'
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Kanalga obuna bo'lish", url=CHANNEL_LINK)],
            [InlineKeyboardButton("Tekshirish", callback_data="check_subscription")]
        ])
        await update.message.reply_text(
            "❗️ Iltimos kanalga botdan foydalanish uchun obuna bo'ling.", reply_markup=keyboard
        )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data != "check_subscription":
        is_subscribed = await check_subscription(user_id, context)
        if not is_subscribed:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Kanalga obuna bo'lish", url=CHANNEL_LINK)],
                [InlineKeyboardButton("Qayta tekshirish", callback_data="check_subscription")]
            ])
            try:
                await query.edit_message_text(
                    "❗️ Iltimos kanalga botdan foydalanish uchun obuna bo'ling.", reply_markup=keyboard
                )
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise
            return

    if data == "check_subscription":
        is_subscribed = await check_subscription(user_id, context)
        if is_subscribed:
            await query.edit_message_text(
                "✅ Siz kanalga obuna bolgansiz! Quyidagi menyudan tanlang:",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Kanalga obuna bo'lish", url=CHANNEL_LINK)],
                [InlineKeyboardButton("Qayta tekshirish", callback_data="check_subscription")]
            ])
            await query.edit_message_text(
                "❗️ Siz kanalga obuna bo'lmagansiz. Iltimos kanalga obuna bo'ling va qayta tekshirish tugmasini bosing.",
                reply_markup=keyboard
            )

    elif data == "halal_cert_evidence":
        cert_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001F4C4 САНИТАРНО-ЭПИДЕМИОЛОГИЧЕСКОЕ", callback_data="cert_sanitary")],
            [InlineKeyboardButton("\U0001F4C4 ВЕТЕРИНАРНОЕ СВИДЕТЕЛЬСТВО", callback_data="cert_veterinary")],
            [InlineKeyboardButton("\U0001F54C HALAL SLAUGHTERING CERTIFICATE", callback_data="cert_halal")],
            [InlineKeyboardButton("\U0001F519 Orqaga", callback_data="back")]
        ])
        await query.edit_message_text("Quyidagi sertifikatlardan birini tanlang:", reply_markup=cert_buttons)

    elif data in CERTIFICATE_IMAGES:
        image_path = CERTIFICATE_IMAGES[data]
        with open(image_path, 'rb') as photo:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=photo)
        await query.answer()

    elif data == "show_video":
        # Show two categories for video selection
        video_buttons = [
            [InlineKeyboardButton("Go'sht so'yilish jarayoni", callback_data="video_process")],
            [InlineKeyboardButton("Go'sht markazlari", callback_data="video_centers")],
            [InlineKeyboardButton('\U0001F519 Orqaga', callback_data='back')]
        ]
        await query.edit_message_text("Videolar kategoriyasini tanlang:", reply_markup=InlineKeyboardMarkup(video_buttons))

    elif data == "video_process":
        video_path = "video/meat_processing.mp4"
        with open(video_path, 'rb') as video:
            await context.bot.send_video(chat_id=query.message.chat_id, video=video, caption="🔪  So'yilish jarayoni")
        await query.answer()

    elif data == "video_centers":
        video_path = "video/second-video.mp4"
        with open(video_path, 'rb') as video:
            await context.bot.send_video(chat_id=query.message.chat_id, video=video, caption="🏢 Taqvo savdo rastalari")
        await query.answer()

    elif data == "meats":
        meats = get_all_meats()
        if meats:
            buttons = []
            row = []
            for idx, (code, name, price, image, amount) in enumerate(meats):
                row.append(InlineKeyboardButton(f"{name}", callback_data=f"meat_{code}"))
                if (idx + 1) % 2 == 0:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([InlineKeyboardButton('\U0001F519 Orqaga', callback_data='back')])
            await query.edit_message_text("Go'shtlardan birini tanlang:", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await query.edit_message_text("Go'shtlar mavjud emas.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='back')]]))

    elif data.startswith("meat_"):
        meat_code = data.split("_", 1)[1]
        meats = get_all_meats()
        meat = next(((c, n, p, i, a) for c, n, p, i, a in meats if c == meat_code), None)
        if meat:
            code, name, price, image, amount = meat
            text = f"<b>{name}</b>\n\n<b>Kod:</b> {code}\n<b>Narx:</b> {price} so'm/{amount}"
            if image:
                try:
                    with open(image, 'rb') as photo:
                        await context.bot.send_photo(chat_id=query.message.chat_id, photo=photo, caption=text, parse_mode='HTML')
                    await query.answer()
                    return
                except Exception as e:
                    logger.error(f"Image send error: {e}")
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='meats')]]))
        else:
            await query.edit_message_text("Go'sht topilmadi.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='meats')]]))

    elif data == "about":
        await query.edit_message_text("\U0001F4D8 Biz haqimizda:\n\n"\
"Biz 'Yunayted Invest' korxonasi O’zbekiston bozorida 4 yil davomida faoliyat yurutib kelamiz\n"\
"Bizning asosiy yo’nalishimiz, muzlatilgan go’sht va go’sht mahsulotlarini ishlab chiqarish\n"\
"Bizning maqsadimiz O’zbekiston bozoriga halol, sifatli va arzon go’sht mahsulotlarini yetkazib berish\n"\
"Biz mustahkam hamkorlik va mahsulot\nsifatini doimiy ravishda ta’minlaymiz", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='back')]]))

    elif data == "contacts":
        contact_buttons = [
            [InlineKeyboardButton("Bosh ofis", callback_data="contact_office")],
            [InlineKeyboardButton("Toshkent shahar bozorlari", callback_data="contact_markets")],
            [InlineKeyboardButton("Operator", callback_data="contact_operator")],
            [InlineKeyboardButton("Call center", callback_data="call-center")],
            [InlineKeyboardButton('\U0001F519 Orqaga', callback_data='back')]
        ]
        await query.edit_message_text("\U0001F4DE Biz bilan bog'lanish uchun bo'limni tanlang:", reply_markup=InlineKeyboardMarkup(contact_buttons))

    elif data == "contact_office":
        office_text = "<b>Bosh ofis:</b>\n+998 99 301 11 18 (Anvar)\n+998 93 390 00 18 (Kozimhon)"
        await query.edit_message_text(office_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='contacts')]]))

    elif data == "contact_markets":
        markets_text = "<b>Toshkent shahar bozorlari:</b>\n+998 97 735 00 03 (Izzatuloh)\n+998 93 587 91 11 (Shaxzod)"
        await query.edit_message_text(markets_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='contacts')]]))

    elif data == "call-center":
        office_text = "<b>Call center:</b>\n+998 55 510 08 08\n+998 55 502 40 40"
        await query.edit_message_text(office_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='contacts')]]))
    
    elif data == "contact_operator":
        operator_text = "<b>Operator:</b>\n+998 99 832 04 27 (Yusuf)\n+998 99 882 40 24 (Akmal)"
        await query.edit_message_text(operator_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('\U0001F519 Orqaga', callback_data='contacts')]]))

    elif data == "back":
        await query.edit_message_text("Asosiy menu:", reply_markup=get_main_menu_keyboard())

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bu buyruqni tanib bolmadi. Iltimos /start buyrug'ini ishlatishni unutmang.")

# --- Main Entrypoint ---
def main():
    if not TG_TOKEN or not CHANNEL_USERNAME or not CHANNEL_LINK:
        raise ValueError("Missing essential env variables: check .env file!")

    app = Application.builder().token(TG_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()