from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import random
import qrcode
from io import BytesIO
import logging
from datetime import datetime
import pickle
import os
from typing import Optional
import jdatetime

# تنظیمات ربات
TOKEN = "8018267062:AAGWgeQsv1lVXf_doknfRQ2w6JCHLZa_jBg"
ADMIN_IDS = [5203173160, 77437019]  # لیست ادمین‌ها
CHANNEL_ID = -1002318262499
CHANNEL_LINK = "https://t.me/sonytelshop"
DATA_FILE = "user_data.pkl"

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# متغیرهای سراسری
robot_active = True
user_wallets = {}
pending_charges = {}
products = {
    "apple": [],  # لیست محصولات اپل
    "vpn": []     # لیست محصولات VPN
}
banned_users = set()
service_requests = {}
user_discounts = {}
user_debts = {}  # ذخیره بدهی‌های کاربران  # ذخیره تخفیفات کاربران

# اطلاعات کارت
card_info = {
    "card_number": "6219861953010591",
    "card_owner": "طاها اعتصام فرد"
}

# تاریخچه خرید کاربران
user_purchases = {}

# اطلاعات کاربران
user_data = {}

def get_jalali_date(dt=None):
    """تبدیل تاریخ میلادی به شمسی"""
    if dt is None:
        dt = datetime.now()
    jalali_date = jdatetime.datetime.fromgregorian(datetime=dt)
    return jalali_date.strftime("%Y-%m-%d %H:%M:%S")

def load_user_data():
    """بارگذاری داده‌های کاربران از فایل"""
    global user_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'rb') as f:
                user_data = pickle.load(f)
            logger.info(f"Loaded user data with {len(user_data)} users")
        else:
            user_data = {}
            logger.info("No user data file found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        user_data = {}

def save_user_data():
    """ذخیره داده‌های کاربران در فایل"""
    try:
        with open(DATA_FILE, 'wb') as f:
            pickle.dump(user_data, f)
        logger.info("User data saved successfully")
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

# بارگذاری اولیه داده‌ها
load_user_data()

async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی عضویت کاربر در کانال"""
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

async def safe_send_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, reply_markup=None, **kwargs):
    """ارسال ایمن پیام با مدیریت خطاها"""
    try:
        return await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

async def safe_edit_message(query, text: str, reply_markup=None, force_edit=False, **kwargs):
    """تابع ایمن برای ویرایش پیام با مدیریت خطاها"""
    try:
        if query and hasattr(query, 'edit_message_text'):
            current_text = query.message.text
            current_markup = query.message.reply_markup
            
            if not force_edit:
                if (text == current_text and 
                    ((reply_markup is None and current_markup is None) or 
                     (reply_markup is not None and current_markup is not None and 
                      str(reply_markup) == str(current_markup)))):
                    return None
            
            return await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                **kwargs
            )
        return None
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        try:
            if query and hasattr(query, 'message'):
                return await query.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    **kwargs
                )
            return None
        except Exception as e2:
            logger.error(f"Error sending new message: {e2}")
            return None

# --- منوها با طراحی جدید ---
def main_menu(user_id):
    """منوی اصلی به صورت دو ستونی و با جابجایی خدمات و فروشگاه"""
    buttons = [
        [InlineKeyboardButton("🛍️ فروشگاه محصولات  🔥", callback_data="store"),
         InlineKeyboardButton("🧰 خدمات ویژه  اپل", callback_data="services")],
        [InlineKeyboardButton("💳 کیف پول  💰", callback_data="wallet"),
         InlineKeyboardButton("🧾  خریدهای من 📦", callback_data="my_purchases")]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton("🧑‍💼 مدیریت ربات ⚙️", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)

def wallet_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 مشاهده موجودی کیف پول 💳", callback_data="balance")],
        [InlineKeyboardButton("➕ شارژ کیف پول از طریق کارت به کارت", callback_data="charge_wallet")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])

def my_purchases_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍏 خریدهای اپل‌آیدی من", callback_data="my_apple_purchases")],
        [InlineKeyboardButton("🔒 خریدهای VPN من", callback_data="my_vpn_purchases")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])

def services_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 فعال‌سازی نات اکتیوی 🔐", callback_data="not_activated")],
        [InlineKeyboardButton("🆘 خدمات اپل‌آیدی اضطراری", callback_data="emergency_service")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن محصول جدید", callback_data="add_product")],
        [InlineKeyboardButton("👥 مدیریت کاربران و لیست خرید", callback_data="manage_users")],
        [InlineKeyboardButton("📝 بررسی درخواست‌های خدمات", callback_data="service_requests")],
        [InlineKeyboardButton("🔄 روشن/خاموش کردن ربات", callback_data="toggle_bot")],
        [InlineKeyboardButton("💳 تنظیمات کیف پول", callback_data="manage_wallet")],
        [InlineKeyboardButton("🎁 مدیریت تخفیفات کاربران", callback_data="manage_discounts")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])
def wallet_menu():
    """منوی کیف پول با طراحی جدید"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 موجودی کیف پول", callback_data="balance"),
         InlineKeyboardButton("➕ شارژ کیف پول", callback_data="charge_wallet")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])

def admin_menu():
    """منوی ادمین با طراحی جدید"""
    return InlineKeyboardMarkup([ 
        [InlineKeyboardButton("➕ افزودن محصول", callback_data="add_product"),
         InlineKeyboardButton("👥 مدیریت کاربران", callback_data="manage_users")],
        [InlineKeyboardButton("📝 درخواست‌ها", callback_data="service_requests"),
         InlineKeyboardButton("🔄 تغییر وضعیت ربات", callback_data="toggle_bot")],
        [InlineKeyboardButton("💳 مدیریت کیف پول", callback_data="manage_wallet"),
         InlineKeyboardButton("🎁 مدیریت تخفیفات", callback_data="manage_discounts")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])

def manage_discounts_menu():
    """منوی مدیریت تخفیفات"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن تخفیف", callback_data="add_discount"),
         InlineKeyboardButton("🗑️ حذف تخفیف", callback_data="remove_discount")],
        [InlineKeyboardButton("📋 لیست تخفیفات", callback_data="list_discounts")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin")]
    ])

def service_requests_menu():
    """منوی درخواست‌های خدمات"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 نات اکتیوی", callback_data="not_activated_requests")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin")]
    ])

def not_activated_requests_menu():
    """منوی درخواست‌های نات اکتیوی"""
    buttons = []
    
    # جمع‌آوری تمام درخواست‌های نات اکتیوی
    requests_list = []
    for user_id, requests in service_requests.items():
        for req in requests:
            if req["type"] == "not_activated":
                requests_list.append((user_id, req))
    
    if not requests_list:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ بازگشت", callback_data="service_requests")]
        ])
    
    # نمایش 4 درخواست در هر صفحه
    for i in range(0, len(requests_list), 4):
        row = []
        for j in range(4):
            if i+j < len(requests_list):
                user_id, req = requests_list[i+j]
                user_info = user_data.get(user_id, {})
                btn_text = f"{user_info.get('full_name', 'کاربر')} - {req['date']}"
                row.append(InlineKeyboardButton(btn_text, callback_data=f"view_not_activated_{user_id}_{req['date']}"))
        if row:
            buttons.append(row)
    
    buttons.append([InlineKeyboardButton("◀️ بازگشت", callback_data="service_requests")])
    
    return InlineKeyboardMarkup(buttons)

def manage_users_menu():
    """منوی مدیریت کاربران با طراحی جدید"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 لیست کاربران", callback_data="users_list"),
         InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="search_user")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin")]
    ])

def manage_wallet_menu():
    """منوی مدیریت کیف پول با طراحی جدید"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تغییر شماره کارت", callback_data="change_card_number"),
         InlineKeyboardButton("✏️ تغییر نام صاحب کارت", callback_data="change_card_owner")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])

def store_menu():
    """منوی فروشگاه با نمایش تعداد محصولات"""
    apple_count = len(products.get("apple", []))
    vpn_count = len(products.get("vpn", []))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🍏 اپل‌آیدی ({apple_count})", callback_data="apple_store"),
         InlineKeyboardButton(f"🔒 VPN ({vpn_count})", callback_data="vpn_store")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])

def services_menu():
    """منوی خدمات"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 فعالسازی نات اکتیوی", callback_data="not_activated")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])

def confirm_service_menu():
    """منوی تایید اطلاعات خدمات"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ارسال", callback_data="confirm_service"),
         InlineKeyboardButton("❌ انصراف", callback_data="cancel_service")]
    ])

def product_buy_menu(category, user_id=None):
    """منوی خرید محصول با نمایش تعداد"""
    count = len(products.get(category, []))
    
    # بررسی تخفیف کاربر
    original_price = products[category][0]['price'] if products.get(category) else 0
    discounted_price = get_discounted_price(user_id, category, original_price) if user_id else original_price
    
    if discounted_price != original_price:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🛒 خرید ({count}) - {discounted_price:,} تومان (تخفیف دار)", callback_data=f"buy_{category}"),
             InlineKeyboardButton("🔙 بازگشت", callback_data="store")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🛒 خرید ({count})", callback_data=f"buy_{category}"),
             InlineKeyboardButton("🔙 بازگشت", callback_data="store")],
        ])

def my_purchases_menu():
    """منوی خریدهای کاربر با طراحی جدید"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍏 اپل‌آیدی", callback_data="my_apple_purchases"),
         InlineKeyboardButton("🔒 VPN", callback_data="my_vpn_purchases")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])

def apple_purchases_menu(user_id):
    """منوی خریدهای اپل با طراحی جدید"""
    if user_id not in user_purchases or "apple" not in user_purchases[user_id] or not user_purchases[user_id]["apple"]:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ بازگشت", callback_data="my_purchases"),
             InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
        ])
    
    buttons = []
    purchases = user_purchases[user_id]["apple"]
    for i in range(0, len(purchases), 2):
        row = []
        if i < len(purchases):
            product = purchases[i]
            row.append(InlineKeyboardButton(f"🍏 {product['id']}", callback_data=f"show_apple_{product['id']}"))
        if i+1 < len(purchases):
            product = purchases[i+1]
            row.append(InlineKeyboardButton(f"🍏 {product['id']}", callback_data=f"show_apple_{product['id']}"))
        if row:
            buttons.append(row)
    
    buttons.append([InlineKeyboardButton("◀️ بازگشت", callback_data="my_purchases"),
                   InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(buttons)

def vpn_purchases_menu(user_id):
    """منوی خریدهای VPN با طراحی جدید"""
    if user_id not in user_purchases or "vpn" not in user_purchases[user_id] or not user_purchases[user_id]["vpn"]:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ بازگشت", callback_data="my_purchases"),
             InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
        ])
    
    buttons = []
    purchases = user_purchases[user_id]["vpn"]
    for i in range(0, len(purchases), 2):
        row = []
        if i < len(purchases):
            product = purchases[i]
            row.append(InlineKeyboardButton(f"🔒 {product['id']}", callback_data=f"show_vpn_{product['id']}"))
        if i+1 < len(purchases):
            product = purchases[i+1]
            row.append(InlineKeyboardButton(f"🔒 {product['id']}", callback_data=f"show_vpn_{product['id']}"))
        if row:
            buttons.append(row)
    
    buttons.append([InlineKeyboardButton("◀️ بازگشت", callback_data="my_purchases"),
                   InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(buttons)

def user_info_menu(user_id):
    """منوی اطلاعات کاربر با طراحی جدید"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📞 {user_data[user_id].get('phone', 'بدون شماره')}", callback_data=f"user_phone_{user_id}")],
        [InlineKeyboardButton("◀️ بازگشت", callback_data="users_list")]
    ])

def user_purchases_menu(user_id):
    """منوی خریدهای کاربر برای ادمین با طراحی جدید"""
    buttons = []
    
    # خریدهای اپل
    apple_purchases = user_purchases.get(user_id, {}).get("apple", [])[-4:]
    for i in range(0, len(apple_purchases), 2):
        row = []
        if i < len(apple_purchases):
            product = apple_purchases[i]
            row.append(InlineKeyboardButton(f"🍏 {product['id']}", callback_data=f"admin_show_apple_{product['id']}_{user_id}"))
        if i+1 < len(apple_purchases):
            product = apple_purchases[i+1]
            row.append(InlineKeyboardButton(f"🍏 {product['id']}", callback_data=f"admin_show_apple_{product['id']}_{user_id}"))
        if row:
            buttons.append(row)
    
    # خریدهای VPN
    vpn_purchases = user_purchases.get(user_id, {}).get("vpn", [])[-4:]
    for i in range(0, len(vpn_purchases), 2):
        row = []
        if i < len(vpn_purchases):
            product = vpn_purchases[i]
            row.append(InlineKeyboardButton(f"🔒 {product['id']}", callback_data=f"admin_show_vpn_{product['id']}_{user_id}"))
        if i+1 < len(vpn_purchases):
            product = vpn_purchases[i+1]
            row.append(InlineKeyboardButton(f"🔒 {product['id']}", callback_data=f"admin_show_vpn_{product['id']}_{user_id}"))
        if row:
            buttons.append(row)
    
    buttons.append([InlineKeyboardButton("◀️ بازگشت", callback_data=f"user_info_{user_id}")])
    
    return InlineKeyboardMarkup(buttons)

# --- توابع جدید برای مدیریت تخفیفات ---
def get_discounted_price(user_id, product_type, original_price):
    """محاسبه قیمت با تخفیف برای کاربر"""
    if user_id in user_discounts and product_type in user_discounts[user_id]:
        discount = user_discounts[user_id][product_type]
        return original_price - (original_price * discount // 100)
    return original_price

async def handle_add_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت افزودن تخفیف"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
        await query.answer("⛔ دسترسی ندارید!")
        return
    
    await safe_edit_message(
        query,
        "➕ افزودن تخفیف\n\nلطفاً آیدی کاربر را وارد کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ بازگشت", callback_data="manage_discounts")]
        ])
    )
    context.user_data["awaiting_discount_user_id"] = True

async def handle_remove_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت حذف تخفیف"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
        await query.answer("⛔ دسترسی ندارید!")
        return
    
    if not user_discounts:
        await safe_edit_message(
            query,
            "❌ هیچ تخفیفی ثبت نشده است!",
            reply_markup=manage_discounts_menu()
        )
        return
    
    buttons = []
    for user_id, discounts in user_discounts.items():
        user_info = user_data.get(user_id, {})
        btn_text = f"{user_info.get('full_name', 'کاربر')} ({user_id})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"remove_discount_{user_id}")])
    
    buttons.append([InlineKeyboardButton("◀️ بازگشت", callback_data="manage_discounts")])
    
    await safe_edit_message(
        query,
        "🗑️ حذف تخفیف\n\nلطفاً کاربر مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_list_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست تخفیفات"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
        await query.answer("⛔ دسترسی ندارید!")
        return
    
    if not user_discounts:
        await safe_edit_message(
            query,
            "❌ هیچ تخفیفی ثبت نشده است!",
            reply_markup=manage_discounts_menu()
        )
        return
    
    text = "📋 لیست تخفیفات:\n\n"
    for user_id, discounts in user_discounts.items():
        user_info = user_data.get(user_id, {})
        text += f"👤 کاربر: {user_info.get('full_name', 'نامشخص')} ({user_id})\n"
        if "apple" in discounts:
            text += f"🍏 اپل‌آیدی: {discounts['apple']}%\n"
        if "vpn" in discounts:
            text += f"🔒 VPN: {discounts['vpn']}%\n"
        text += "\n"
    
    await safe_edit_message(
        query,
        text,
        reply_markup=manage_discounts_menu()
    )

async def handle_remove_specific_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف تخفیف برای کاربر خاص"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
        await query.answer("⛔ دسترسی ندارید!")
        return
    
    user_id = int(query.data.split("_")[2])
    if user_id in user_discounts:
        del user_discounts[user_id]
        await safe_edit_message(
            query,
            f"✅ تخفیف کاربر با آیدی {user_id} با موفقیت حذف شد!",
            reply_markup=manage_discounts_menu()
        )
    else:
        await safe_edit_message(
            query,
            f"❌ کاربر با آیدی {user_id} تخفیفی ندارد!",
            reply_markup=manage_discounts_menu()
        )

# --- توابع اصلی ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی مجدد عضویت کاربر"""
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
    
    if await is_user_member(user_id, context):
        await safe_send_message(
            context,
            chat_id=user_id,
            text="✅ عضویت شما تایید شد!\n\nسلام! به ربات فروشگاه سونی تل خوش آمدید 👋",
            reply_markup=main_menu(user_id))
        
        if query:
            try:
                await query.delete_message()
            except Exception as e:
                logger.error(f"Error deleting message: {e}")
    else:
        if query:
            await query.answer("⚠️ هنوز در کانال عضو نشده‌اید! لطفاً ابتدا عضو شوید و سپس دکمه را بزنید.", show_alert=True)

async def membership_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی عضویت کاربر و نمایش پیام مناسب"""
    user_id = update.effective_user.id
    
    if user_id in ADMIN_IDS:  # ادمین‌ها از بررسی عضویت معاف هستند
        return True
        
    if not await is_user_member(user_id, context):
        query = update.callback_query if hasattr(update, 'callback_query') else None
        
        if query is not None:
            await query.answer()
            await safe_edit_message(
                query,
                f"⚠️ برای استفاده از ربات، باید در کانال ما عضو شوید:\n{CHANNEL_LINK}\n"
                "پس از عضویت، دکمه زیر را بزنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("عضویت در کانال", url=CHANNEL_LINK)],
                    [InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")]
                ]))
        else:
            await safe_send_message(
                context,
                chat_id=user_id,
                text=f"⚠️ برای استفاده از ربات، باید در کانال ما عضو شوید:\n{CHANNEL_LINK}\n"
                     "پس از عضویت، دکمه زیر را بزنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("عضویت در کانال", url=CHANNEL_LINK)],
                    [InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")]
                ]))
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع ربات"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    # ذخیره اطلاعات کاربر اگر وجود نداشته باشد
    if user_id not in user_data:
        user_data[user_id] = {
            "username": user.username,
            "full_name": user.full_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "join_date": get_jalali_date(),
            "language_code": user.language_code
        }
        save_user_data()
    
    logger.info(f"User started/restarted: {user_id} - {user.full_name}")

    # بررسی مسدود بودن کاربر (برای ادمین‌ها معاف)
    if user_id in banned_users and user_id not in ADMIN_IDS:  # ادمین‌ها نمی‌توانند مسدود شوند
        await safe_send_message(
            context,
            chat_id=user_id,
            text="⛔ دسترسی شما به ربات مسدود شده است!"
        )
        return
    
    # بررسی شماره تلفن فقط برای کاربران جدید
    if "phone" not in user_data.get(user_id, {}) and user_id not in ADMIN_IDS:  # ادمین‌ها نیازی به ثبت شماره ندارند
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 اشتراک گذاری شماره تلفن", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await update.message.reply_text(
            "📱 لطفاً برای ادامه، شماره تلفن خود را با استفاده از دکمه زیر به اشتراک بگذارید:",
            reply_markup=keyboard
        )
        return
    
    if not await membership_check(update, context):
        return
    
    await show_main_menu(update, context, user_id)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """نمایش منوی اصلی به کاربر"""
    if update.message:
        await update.message.reply_text(
            "سلام! به ربات فروشگاه سونی تل خوش آمدید 👋",
            reply_markup=main_menu(user_id)
        )
    else:
        await safe_send_message(
            context,
            chat_id=user_id,
            text="سلام! به ربات فروشگاه خوش آمدید 👋",
            reply_markup=main_menu(user_id)
        )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دریافت شماره تلفن کاربر"""
    user_id = update.effective_user.id
    contact = update.message.contact
    
    if contact.user_id != user_id:
        await update.message.reply_text("⚠️ لطفاً شماره تلفن خود را به اشتراک بگذارید!")
        return
    
    # ذخیره شماره تلفن کاربر
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]["phone"] = contact.phone_number
    save_user_data()
    
    logger.info(f"User {user_id} shared phone number: {contact.phone_number}")
    
    # حذف کیبورد
    await update.message.reply_text(
        "✅ شماره تلفن شما با موفقیت ثبت شد!",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # نمایش منوی اصلی
    await show_main_menu(update, context, user_id)

async def handle_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست کاربران"""
    query = update.callback_query
    await query.answer()
    
    if not user_data:
        await safe_edit_message(
            query,
            "❌ هیچ کاربری در سیستم ثبت نشده است!",
            reply_markup=manage_users_menu()
        )
        return
    
    buttons = []
    for user_id, data in user_data.items():
        try:
            username = f"@{data['username']}" if data.get('username') else "بدون یوزرنیم"
            phone = data.get('phone', 'بدون شماره')
            btn_text = f"{data.get('full_name', 'کاربر')} ({phone})"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"user_info_{user_id}")])
        except Exception as e:
            logger.error(f"Error processing user {user_id}: {e}")
            continue
    
    buttons.append([InlineKeyboardButton("◀️ بازگشت", callback_data="manage_users")])
    
    await safe_edit_message(
        query,
        f"📋 لیست کاربران ({len(user_data)} کاربر)\n\nبرای مشاهده جزئیات روی هر کاربر کلیک کنید:",
        reply_markup=InlineKeyboardMarkup(buttons),
        force_edit=True
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش کلیک روی دکمه‌های اینلاین"""
    global robot_active
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id

    # بررسی مسدود بودن کاربر (برای ادمین‌ها معاف)
    if user_id in banned_users and user_id not in ADMIN_IDS:
        await safe_send_message(
            context,
            chat_id=user_id,
            text="⛔ دسترسی شما به ربات مسدود شده است!"
        )
        return

    # بررسی عضویت در کانال (برای ادمین‌ها معاف)
    if user_id not in ADMIN_IDS and not await is_user_member(user_id, context):
        if query:
            await safe_edit_message(
                query,
                f"⚠️ برای استفاده از ربات، باید در کانال ما عضو شوید:\n{CHANNEL_LINK}\n"
                "پس از عضویت، دکمه زیر را بزنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("عضویت در کانال", url=CHANNEL_LINK)],
                    [InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")]
                ]))
        else:
            await safe_send_message(
                context,
                chat_id=user_id,
                text=f"⚠️ برای استفاده از ربات، باید در کانال ما عضو شوید:\n{CHANNEL_LINK}\n"
                     "پس از عضویت، دکمه زیر را بزنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("عضویت در کانال", url=CHANNEL_LINK)],
                    [InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")]
                ]))
        return

    # بررسی وضعیت ربات
    if not robot_active and user_id not in ADMIN_IDS:
        if query:
            await safe_edit_message(query, "⛔ ربات موقتاً غیرفعال است!", reply_markup=main_menu(user_id))
        else:
            await safe_send_message(context, user_id, "⛔ ربات موقتاً غیرفعال است!", reply_markup=main_menu(user_id))
        return

    if not query:
        return

    if query.data == "wallet":
        await safe_edit_message(
            query,
            "💰 مدیریت کیف پول\n\n"
            f"شماره کارت: {card_info['card_number']}\n"
            f"به نام: {card_info['card_owner']}",
            reply_markup=wallet_menu(),
            force_edit=True
        )
    elif query.data == "balance":
        balance = user_wallets.get(user_id, 0)
        await safe_edit_message(query, f"💳 موجودی شما: {balance:,} تومان", reply_markup=wallet_menu())
    elif query.data == "charge_wallet":
        await safe_edit_message(query, "💵 لطفاً مبلغ شارژ را به تومان وارد کنید:")
        context.user_data["awaiting_amount"] = True
    elif query.data == "store":
        await safe_edit_message(query, "🛒 فروشگاه", reply_markup=store_menu())
    elif query.data == "apple_store":
        if not products.get("apple", []):
            await safe_edit_message(query, "❌ محصولی موجود نیست!", reply_markup=product_buy_menu("apple", user_id))
        else:
            product = products["apple"][0]
            original_price = product['price']
            discounted_price = get_discounted_price(user_id, "apple", original_price)
            
            if discounted_price != original_price:
                message = (
                    f"🍏 اپل‌آیدی\n\n"
                    f"💰 قیمت اصلی: {original_price:,} تومان\n"
                    f"🎁 قیمت با تخفیف: {discounted_price:,} تومان"
                )
            else:
                message = f"🍏 اپل‌آیدی\n\n💰 قیمت: {original_price:,} تومان"
            
            await safe_edit_message(
                query,
                message,
                reply_markup=product_buy_menu("apple", user_id))
    elif query.data == "vpn_store":
        if not products.get("vpn", []):
            await safe_edit_message(query, "❌ محصولی موجود نیست!", reply_markup=product_buy_menu("vpn", user_id))
        else:
            product = products["vpn"][0]
            original_price = product['price']
            discounted_price = get_discounted_price(user_id, "vpn", original_price)
            
            if discounted_price != original_price:
                message = (
                    f"🔒 VPN\n\n"
                    f"💰 قیمت اصلی: {original_price:,} تومان\n"
                    f"🎁 قیمت با تخفیف: {discounted_price:,} تومان\n\n"
                    "📝 این VPN یک ماهه با 20 گیگابایت حجم است"
                )
            else:
                message = (
                    f"🔒 VPN\n\n💰 قیمت: {original_price:,} تومان\n\n"
                    "📝 این VPN یک ماهه با 20 گیگابایت حجم است"
                )
            
            await safe_edit_message(
                query,
                message,
                reply_markup=product_buy_menu("vpn", user_id))
    elif query.data.startswith("buy_"):
        category = query.data.split("_")[1]
        if category == "apple":
            await handle_apple_purchase(query, user_id, context)
        elif category == "vpn":
            await handle_vpn_purchase(query, user_id, context)
    elif query.data == "admin":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(
                query,
                "⚙️ پنل مدیریت",
                reply_markup=admin_menu(),
                force_edit=True
            )
        else:
            await query.answer("⛔ دسترسی ندارید!")
    elif query.data == "add_product":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(query, "📝 لطفاً نوع محصول را انتخاب کنید (apple یا vpn):")
            context.user_data["awaiting_product_type"] = True
    elif query.data == "toggle_bot":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            robot_active = not robot_active
            status = "✅ ربات فعال شد" if robot_active else "🛑 ربات غیرفعال شد"
            await safe_edit_message(query, status, reply_markup=admin_menu())
    elif query.data == "manage_wallet":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(
                query,
                "💳 مدیریت کیف پول\n\n1. تغییر شماره کارت\n2. تغییر نام صاحب کارت",
                reply_markup=manage_wallet_menu()
            )
    elif query.data == "change_card_number":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(query, "📱 لطفاً شماره کارت جدید را وارد کنید:")
            context.user_data["awaiting_card_number"] = True
    elif query.data == "change_card_owner":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(query, "📝 لطفاً نام صاحب کارت جدید را وارد کنید:")
            context.user_data["awaiting_card_owner"] = True
    elif query.data == "back_to_main":
        await safe_edit_message(query, "🏠 منوی اصلی", reply_markup=main_menu(user_id))
    elif query.data == "my_purchases":
        await safe_edit_message(
            query,
            "📦 خریدهای من\n\nلطفاً دسته‌بندی مورد نظر را انتخاب کنید:",
            reply_markup=my_purchases_menu()
        )
    elif query.data == "my_apple_purchases":
        if user_id not in user_purchases or "apple" not in user_purchases[user_id] or not user_purchases[user_id]["apple"]:
            await safe_edit_message(
                query,
                "❌ شما تاکنون هیچ خرید اپل‌آیدی نداشته‌اید!",
                reply_markup=my_purchases_menu()
            )
        else:
            await safe_edit_message(
                query,
                "🍏 خریدهای اپل‌آیدی شما\n\nلطفاً یکی از خریدها را انتخاب کنید:",
                reply_markup=apple_purchases_menu(user_id))
    elif query.data == "my_vpn_purchases":
        if user_id not in user_purchases or "vpn" not in user_purchases[user_id] or not user_purchases[user_id]["vpn"]:
            await safe_edit_message(
                query,
                "❌ شما تاکنون هیچ خرید VPN نداشته‌اید!",
                reply_markup=my_purchases_menu()
            )
        else:
            await safe_edit_message(
                query,
                "🔒 خریدهای VPN شما\n\nلطفاً یکی از خریدها را انتخاب کنید:",
                reply_markup=vpn_purchases_menu(user_id)
            )
    elif query.data.startswith("show_apple_"):
        product_id = int(query.data.split("_")[2])
        user_id = query.from_user.id
        
        if user_id in user_purchases and "apple" in user_purchases[user_id]:
            for product in user_purchases[user_id]["apple"]:
                if product["id"] == product_id:
                    await safe_edit_message(
                        query,
                        f"🍏 اطلاعات خرید اپل‌آیدی\n\n"
                        f"{product['description']}\n"
                        f"💰 قیمت: {product['price']:,} تومان\n"
                        f"📅 تاریخ خرید: {product.get('purchase_date', 'نامشخص')}",
                        reply_markup=apple_purchases_menu(user_id))
                    break
    elif query.data.startswith("show_vpn_"):
        product_id = int(query.data.split("_")[2])
        user_id = query.from_user.id
        
        if user_id in user_purchases and "vpn" in user_purchases[user_id]:
            for product in user_purchases[user_id]["vpn"]:
                if product["id"] == product_id:
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(product['link'])
                    qr.make(fit=True)
                    
                    img = qr.make_image(fill_color="black", back_color="white")
                    bio = BytesIO()
                    bio.name = 'qr_code.png'
                    img.save(bio, 'PNG')
                    bio.seek(0)
                    
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=bio,
                        caption=f"🔒 اطلاعات خرید VPN\n\n"
                                f"🆔 کد محصول: {product['id']}\n"
                                f"🔗 لینک: {product['link']}\n"
                                f"💰 قیمت: {product['price']:,} تومان\n"
                                f"📅 تاریخ خرید: {product.get('purchase_date', 'نامشخص')}\n\n"
                                "📝 این VPN یک ماهه با 20 گیگابایت حجم است",
                        reply_markup=vpn_purchases_menu(user_id))
                    
                    try:
                        await query.delete_message()
                    except Exception as e:
                        logger.error(f"Error deleting message: {e}")
                    break
    elif query.data == "manage_users":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(
                query,
                "👥 مدیریت کاربران\n\nلطفاً گزینه مورد نظر را انتخاب کنید:",
                reply_markup=manage_users_menu(),
                force_edit=True
            )
    elif query.data == "users_list":
        await handle_users_list(update, context)
    elif query.data == "search_user":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(
                query,
                "🔍 لطفاً آیدی کاربر را وارد کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ بازگشت", callback_data="manage_users")]
                ])
            )
            context.user_data["awaiting_user_id"] = True
    elif query.data.startswith("user_info_"):
        target_user_id = int(query.data.split("_")[2])
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await show_user_info(query, target_user_id, context)
    elif query.data.startswith("user_phone_"):
        target_user_id = int(query.data.split("_")[2])
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await show_user_purchases(query, target_user_id, context)
    elif query.data.startswith("admin_show_apple_"):
        parts = query.data.split("_")
        product_id = int(parts[3])
        target_user_id = int(parts[4])
        
        if target_user_id in user_purchases and "apple" in user_purchases[target_user_id]:
            for product in user_purchases[target_user_id]["apple"]:
                if product["id"] == product_id:
                    await safe_edit_message(
                        query,
                        f"🍏 اطلاعات خرید اپل‌آیدی کاربر\n\n"
                        f"🆔 آیدی کاربر: {target_user_id}\n"
                        f"👤 نام: {user_data[target_user_id]['full_name']}\n"
                        f"📞 تلفن: {user_data[target_user_id].get('phone', 'نامشخص')}\n\n"
                        f"🆔 کد محصول: {product['id']}\n"
                        f"📝 توضیحات:\n{product['description']}\n"
                        f"💰 قیمت: {product['price']:,} تومان\n"
                        f"📅 تاریخ خرید: {product.get('purchase_date', 'نامشخص')}",
                        reply_markup=user_purchases_menu(target_user_id))
                    break
    elif query.data.startswith("admin_show_vpn_"):
        parts = query.data.split("_")
        product_id = int(parts[3])
        target_user_id = int(parts[4])
        
        if target_user_id in user_purchases and "vpn" in user_purchases[target_user_id]:
            for product in user_purchases[target_user_id]["vpn"]:
                if product["id"] == product_id:
                    await safe_edit_message(
                        query,
                        f"🔒 اطلاعات خرید VPN کاربر\n\n"
                        f"🆔 آیدی کاربر: {target_user_id}\n"
                        f"👤 نام: {user_data[target_user_id]['full_name']}\n"
                        f"📞 تلفن: {user_data[target_user_id].get('phone', 'نامشخص')}\n\n"
                        f"🆔 کد محصول: {product['id']}\n"
                        f"🔗 لینک: {product['link']}\n"
                        f"💰 قیمت: {product['price']:,} تومان\n"
                        f"📅 تاریخ خرید: {product.get('purchase_date', 'نامشخص')}",
                        reply_markup=user_purchases_menu(target_user_id))
                    break
    elif query.data == "services":
        await safe_edit_message(
            query,
            "🛠️ خدمات\n\nلطفاً خدمت مورد نظر خود را انتخاب کنید:",
            reply_markup=services_menu()
        )
    elif query.data == "not_activated":
        context.user_data["awaiting_service_info"] = True
        context.user_data["current_step"] = 1
        
        service_info = (
            "🔓 فعالسازی نات اکتیوی\n\n"
            "لطفاً اطلاعات زیر را به ترتیب ارسال کنید:\n\n"
            "1. ایمیل اپل آیدی\n"
            "2. پسورد ایمیل\n"
            "3. عکس واضح از پشت جعبه دستگاه\n"
            "4. اسکرین شات از صفحه iCloud گوشی\n"
            "5. اسکرین شات از صفحه About دستگاه\n"
            "6. اسکرین شات از شماره سریال دستگاه\n\n"
            "⚠️ توجه:\n"
            "- جیمیل باید در دسترس باشد\n"
            "- مدت زمان فرایند 20 روز کاری میباشد\n"
            "- هزینه فرایند حدود 6 میلیون تومان میباشد که به صورت کارت به کارت باید پرداخت شود\n"
            "- در صورت عدم موفقیت، مبلغ بازگشت داده خواهد شد\n\n"
            "لطفاً ایمیل اپل آیدی را ارسال کنید:"
        )
        
        await safe_edit_message(
            query,
            service_info,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ انصراف", callback_data="cancel_service")]
            ])
        )
    elif query.data == "confirm_service":
        user_id = query.from_user.id
        if "service_data" not in context.user_data:
            await query.answer("⚠️ اطلاعات خدمات یافت نشد!")
            return
            
        service_data = context.user_data["service_data"]
        
        # ارسال اطلاعات به ادمین
        admin_message = (
            f"📌 درخواست جدید برای فعالسازی نات اکتیوی\n\n"
            f"👤 کاربر: {user_data[user_id]['full_name']}\n"
            f"🆔 آیدی: {user_id}\n"
            f"📞 تلفن: {user_data[user_id].get('phone', 'ثبت نشده')}\n\n"
            f"📧 ایمیل اپل آیدی: {service_data['apple_email']}\n"
            f"🔑 پسورد ایمیل: {service_data['apple_password']}\n\n"
            f"📅 تاریخ درخواست: {get_jalali_date()}\n\n"
            f"⚠️ نکات:\n"
            f"- هزینه فرایند: 6,000,000 تومان\n"
            f"- مدت زمان: 20 روز کاری\n"
            f"- در صورت عدم موفقیت، مبلغ بازگشت داده خواهد شد"
        )
        
        try:
            # ارسال پیام متنی اول
            await context.bot.send_message(
                chat_id=ADMIN_IDS[0],  # ارسال به اولین ادمین
                text=admin_message
            )
            
            # ارسال عکس‌ها به صورت جداگانه
            await context.bot.send_photo(
                chat_id=ADMIN_IDS[0],
                photo=service_data["box_photo"],
                caption="عکس پشت جعبه دستگاه"
            )
            
            await context.bot.send_photo(
                chat_id=ADMIN_IDS[0],
                photo=service_data["icloud_screenshot"],
                caption="اسکرین شات از صفحه iCloud"
            )
            
            await context.bot.send_photo(
                chat_id=ADMIN_IDS[0],
                photo=service_data["about_screenshot"],
                caption="اسکرین شات از صفحه About"
            )
            
            await context.bot.send_photo(
                chat_id=ADMIN_IDS[0],
                photo=service_data["serial_screenshot"],
                caption="اسکرین شات از شماره سریال دستگاه"
            )
            
            # ذخیره درخواست
            if user_id not in service_requests:
                service_requests[user_id] = []
                
            service_requests[user_id].append({
                "type": "not_activated",
                "data": service_data,
                "date": get_jalali_date(),
                "status": "pending"
            })
            
            await safe_edit_message(
                query,
                "✅ درخواست شما با موفقیت ثبت شد!\n\n"
                "📌 اطلاعات درخواست:\n"
                f"📧 ایمیل: {service_data['apple_email']}\n"
                f"📅 تاریخ: {get_jalali_date()}\n\n"
                "🔹 لطفاً برای ادامه مراحل با پشتیبانی در تماس باشید.",
                reply_markup=main_menu(user_id)
            )
            
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error sending service request: {e}")
            await safe_edit_message(
                query,
                "⚠️ خطایی در ارسال درخواست رخ داد. لطفاً دوباره تلاش کنید.",
                reply_markup=services_menu()
            )
            
    elif query.data == "cancel_service":
        user_id = query.from_user.id
        context.user_data.clear()
        await safe_edit_message(
            query,
            "❌ درخواست خدمات لغو شد.",
            reply_markup=services_menu()
        )
    elif query.data == "service_requests":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(
                query,
                "📝 مدیریت درخواست‌های خدمات\n\nلطفاً نوع خدمت را انتخاب کنید:",
                reply_markup=service_requests_menu()
            )
    elif query.data == "not_activated_requests":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(
                query,
                "🔓 درخواست‌های نات اکتیوی\n\nلیست درخواست‌های اخیر:",
                reply_markup=not_activated_requests_menu()
            )
    elif query.data.startswith("view_not_activated_"):
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            parts = query.data.split("_")
            target_user_id = int(parts[3])
            req_date = "_".join(parts[4:])
            
            if target_user_id in service_requests:
                for req in service_requests[target_user_id]:
                    if req["type"] == "not_activated" and req["date"] == req_date:
                        service_data = req["data"]
                        user_info = user_data.get(target_user_id, {})
                        
                        message_text = (
                            f"🔍 جزئیات درخواست نات اکتیوی\n\n"
                            f"👤 کاربر: {user_info.get('full_name', 'نامشخص')}\n"
                            f"🆔 آیدی: {target_user_id}\n"
                            f"📞 تلفن: {user_info.get('phone', 'ثبت نشده')}\n\n"
                            f"📧 ایمیل اپل آیدی: {service_data['apple_email']}\n"
                            f"🔑 پسورد ایمیل: {service_data['apple_password']}\n\n"
                            f"📅 تاریخ درخواست: {req['date']}\n"
                            f"📌 وضعیت: {req['status']}\n\n"
                            f"⚠️ نکات:\n"
                            f"- هزینه فرایند: 6,000,000 تومان\n"
                            f"- مدت زمان: 20 روز کاری\n"
                            f"- در صورت عدم موفقیت، مبلغ بازگشت داده خواهد شد"
                        )
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=message_text
                        )
                        
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=service_data["box_photo"],
                            caption="عکس پشت جعبه دستگاه"
                        )
                        
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=service_data["icloud_screenshot"],
                            caption="اسکرین شات از صفحه iCloud"
                        )
                        
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=service_data["about_screenshot"],
                            caption="اسکرین شات از صفحه About"
                        )
                        
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=service_data["serial_screenshot"],
                            caption="اسکرین شات از شماره سریال دستگاه"
                        )
                        
                        try:
                            await query.delete_message()
                        except Exception as e:
                            logger.error(f"Error deleting message: {e}")
                        break
    elif query.data == "manage_discounts":
        if user_id in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
            await safe_edit_message(
                query,
                "🎁 مدیریت تخفیفات\n\nلطفاً گزینه مورد نظر را انتخاب کنید:",
                reply_markup=manage_discounts_menu()
            )
    elif query.data == "add_discount":
        await handle_add_discount(update, context)
    elif query.data == "remove_discount":
        await handle_remove_discount(update, context)
    elif query.data == "list_discounts":
        await handle_list_discounts(update, context)
    elif query.data.startswith("remove_discount_"):
        await handle_remove_specific_discount(update, context)

async def handle_apple_purchase(query, user_id, context):
    """مدیریت خرید محصول اپل"""
    if not products.get("apple", []):
        await safe_edit_message(query, "❌ محصولی موجود نیست!", reply_markup=product_buy_menu("apple", user_id))
        return
    
    product = products["apple"][0]
    original_price = product['price']
    discounted_price = get_discounted_price(user_id, "apple", original_price)
    balance = user_wallets.get(user_id, 0)
    
    if balance < discounted_price:
        await safe_edit_message(
            query,
            f"⚠️ موجودی کافی نیست!\n\n💰 موجودی شما: {balance:,} تومان\n💵 قیمت محصول: {discounted_price:,} تومان",
            reply_markup=product_buy_menu("apple", user_id))
        return
    
    user_wallets[user_id] = balance - discounted_price
    sold_product = products["apple"].pop(0)
    
    if user_id not in user_purchases:
        user_purchases[user_id] = {"apple": [], "vpn": []}
    
    product_copy = {
        "id": sold_product["id"],
        "description": f"🆔 کد محصول: {sold_product['id']}\n{sold_product['description']}",
        "price": discounted_price,
        "original_price": original_price,
        "purchase_date": get_jalali_date()
    }
    user_purchases[user_id]["apple"].append(product_copy)
    
    # ارسال پیام به کاربر
    message = (
        f"🎉 خرید موفق!\n\n🔑 اطلاعات محصول:\n{product_copy['description']}\n"
        f"💰 قیمت اصلی: {original_price:,} تومان\n"
        f"🎁 قیمت با تخفیف: {discounted_price:,} تومان\n"
        f"💳 مبلغ کسر شده: {discounted_price:,} تومان\n"
        f"💳 موجودی جدید: {user_wallets[user_id]:,} تومان\n"
        f"📅 تاریخ خرید: {product_copy['purchase_date']}"
    )
    
    await safe_send_message(
        context,
        chat_id=user_id,
        text=message,
        reply_markup=main_menu(user_id))
    
    # ارسال پیام به ادمین‌ها
    user_info = user_data.get(user_id, {})
    admin_message = (
        f"📌 خرید جدید - اپل‌آیدی\n\n"
        f"👤 کاربر: {user_info.get('full_name', 'نامشخص')}\n"
        f"🆔 آیدی: {user_id}\n"
        f"📞 تلفن: {user_info.get('phone', 'ثبت نشده')}\n\n"
        f"🛒 محصول خریداری شده:\n"
        f"{product_copy['description']}\n"
        f"💰 قیمت اصلی: {original_price:,} تومان\n"
        f"🎁 قیمت با تخفیف: {discounted_price:,} تومان\n"
        f"📅 تاریخ خرید: {product_copy['purchase_date']}"
    )
    
    # ارسال به همه ادمین‌ها
    for admin_id in ADMIN_IDS:
        await safe_send_message(
            context,
            chat_id=admin_id,
            text=admin_message
        )
    
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

async def handle_vpn_purchase(query, user_id, context):
    """مدیریت خرید محصول VPN"""
    if not products.get("vpn", []):
        await safe_edit_message(query, "❌ محصولی موجود نیست!", reply_markup=product_buy_menu("vpn", user_id))
        return
    
    product = products["vpn"][0]
    original_price = product['price']
    discounted_price = get_discounted_price(user_id, "vpn", original_price)
    balance = user_wallets.get(user_id, 0)
    
    if balance < discounted_price:
        await safe_edit_message(
            query,
            f"⚠️ موجودی کافی نیست!\n\n💰 موجودی شما: {balance:,} تومان\n💵 قیمت محصول: {discounted_price:,} تومان",
            reply_markup=product_buy_menu("vpn", user_id))
        return
    
    user_wallets[user_id] = balance - discounted_price
    sold_product = products["vpn"].pop(0)
    
    if user_id not in user_purchases:
        user_purchases[user_id] = {"apple": [], "vpn": []}
    
    product_copy = {
        "id": sold_product["id"],
        "price": discounted_price,
        "original_price": original_price,
        "link": sold_product["link"],
        "purchase_date": get_jalali_date()
    }
    user_purchases[user_id]["vpn"].append(product_copy)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(product_copy['link'])
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = 'qr_code.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    
    # ارسال پیام به کاربر
    message = (
        f"🎉 خرید موفق!\n\n"
        f"🔒 اطلاعات VPN\n\n"
        f"🆔 کد محصول: {product_copy['id']}\n"
        f"🔗 لینک: {product_copy['link']}\n\n"
        f"💰 قیمت اصلی: {original_price:,} تومان\n"
        f"🎁 قیمت با تخفیف: {discounted_price:,} تومان\n"
        f"💳 مبلغ کسر شده: {discounted_price:,} تومان\n"
        f"💳 موجودی جدید: {user_wallets[user_id]:,} تومان\n"
        f"📅 تاریخ خرید: {product_copy['purchase_date']}\n\n"
        "📝 این VPN یک ماهه با 20 گیگابایت حجم است"
    )
    
    await context.bot.send_photo(
        chat_id=user_id,
        photo=bio,
        caption=message,
        reply_markup=main_menu(user_id))
    
    # ارسال پیام به ادمین‌ها
    user_info = user_data.get(user_id, {})
    admin_message = (
        f"📌 خرید جدید - VPN\n\n"
        f"👤 کاربر: {user_info.get('full_name', 'نامشخص')}\n"
        f"🆔 آیدی: {user_id}\n"
        f"📞 تلفن: {user_info.get('phone', 'ثبت نشده')}\n\n"
        f"🛒 محصول خریداری شده:\n"
        f"🆔 کد محصول: {product_copy['id']}\n"
        f"🔗 لینک: {product_copy['link']}\n"
        f"💰 قیمت اصلی: {original_price:,} تومان\n"
        f"🎁 قیمت با تخفیف: {discounted_price:,} تومان\n"
        f"📅 تاریخ خرید: {product_copy['purchase_date']}"
    )
    
    # ارسال به همه ادمین‌ها
    for admin_id in ADMIN_IDS:
        await safe_send_message(
            context,
            chat_id=admin_id,
            text=admin_message
        )
    
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

async def show_user_info(query, target_user_id, context):
    """نمایش اطلاعات کاربر برای ادمین"""
    if target_user_id not in user_data:
        await query.answer("❌ کاربر یافت نشد!")
        return
    
    user_info = user_data[target_user_id]
    username = f"@{user_info['username']}" if user_info.get('username') else "بدون یوزرنیم"
    balance = user_wallets.get(target_user_id, 0)
    is_banned = target_user_id in banned_users
    phone = user_info.get('phone', 'ثبت نشده')
    
    # اطلاعات تخفیف
    discount_info = ""
    if target_user_id in user_discounts:
        discounts = user_discounts[target_user_id]
        if "apple" in discounts:
            discount_info += f"🍏 اپل‌آیدی: {discounts['apple']}%\n"
        if "vpn" in discounts:
            discount_info += f"🔒 VPN: {discounts['vpn']}%\n"
    
    text = (
        f"👤 اطلاعات کاربر\n\n"
        f"🆔 آیدی: {target_user_id}\n"
        f"👤 نام: {user_info.get('full_name', 'نامشخص')}\n"
        f"📌 یوزرنیم: {username}\n"
        f"📞 تلفن: {phone}\n"
        f"💰 موجودی: {balance:,} تومان\n"
        f"📅 تاریخ عضویت: {user_info.get('join_date', 'نامشخص')}\n"
        f"🚫 وضعیت: {'مسدود شده' if is_banned else 'عادی'}\n\n"
        f"🎁 تخفیفات:\n{discount_info if discount_info else 'بدون تخفیف'}"
    )
    
    await safe_edit_message(
        query,
        text,
        reply_markup=user_info_menu(target_user_id),
        force_edit=True
    )

async def show_user_purchases(query, target_user_id, context):
    """نمایش خریدهای کاربر برای ادمین"""
    if target_user_id not in user_data:
        await query.answer("❌ کاربر یافت نشد!")
        return
    
    user_info = user_data[target_user_id]
    
    text = (
        f"📦 خریدهای کاربر\n\n"
        f"🆔 آیدی: {target_user_id}\n"
        f"👤 نام: {user_info.get('full_name', 'نامشخص')}\n"
        f"📞 تلفن: {user_info.get('phone', 'نامشخص')}\n\n"
        f"📝 4 خرید آخر کاربر:"
    )
    
    await safe_edit_message(
        query,
        text,
        reply_markup=user_purchases_menu(target_user_id),
        force_edit=True
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت پیام‌های متنی و تصاویر"""
    user_id = update.effective_user.id
    text = update.message.text if update.message.text else ""

    # بررسی مسدود بودن کاربر (برای ادمین‌ها معاف)
    if user_id in banned_users and user_id not in ADMIN_IDS:
        await safe_send_message(
            context,
            chat_id=user_id,
            text="⛔ دسترسی شما به ربات مسدود شده است!"
        )
        return

    # بررسی عضویت در کانال (برای ادمین‌ها معاف)
    if user_id not in ADMIN_IDS and not await is_user_member(user_id, context):
        await safe_send_message(
            context,
            chat_id=user_id,
            text=f"⚠️ برای استفاده از ربات، باید در کانال ما عضو شوید:\n{CHANNEL_LINK}\n"
                 "پس از عضویت، دکمه زیر را بزنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("عضویت در کانال", url=CHANNEL_LINK)],
                [InlineKeyboardButton("✅ عضو شدم", callback_data="check_membership")]
            ]))
        return

    if context.user_data.get("awaiting_card_number"):
        card_number = text
        card_info["card_number"] = card_number
        await safe_send_message(
            context,
            chat_id=user_id,
            text=f"✅ شماره کارت جدید با موفقیت ثبت شد: {card_number}",
            reply_markup=admin_menu())
        context.user_data.clear()

    elif context.user_data.get("awaiting_card_owner"):
        card_owner = text
        card_info["card_owner"] = card_owner
        await safe_send_message(
            context,
            chat_id=user_id,
            text=f"✅ نام صاحب کارت جدید با موفقیت ثبت شد: {card_owner}",
            reply_markup=admin_menu())
        context.user_data.clear()

    elif context.user_data.get("awaiting_amount"):
        try:
            amount = int(text)
            if amount <= 0:
                await safe_send_message(context, user_id, "⚠️ مبلغ باید بیشتر از صفر باشد!")
                return
            
            pending_charges[user_id] = {"amount": amount}
            await safe_send_message(context, user_id, "📎 لطفاً تصویر فیش پرداختی را ارسال کنید:")
            context.user_data["awaiting_amount"] = False
            context.user_data["awaiting_receipt"] = True
        except ValueError:
            await safe_send_message(context, user_id, "⚠️ لطفاً فقط عدد وارد کنید!")

    elif context.user_data.get("awaiting_receipt") and update.message.photo:
        receipt = update.message.photo[-1].file_id
        pending_charges[user_id]["receipt"] = receipt
        amount = pending_charges[user_id]["amount"]
        
        await safe_send_message(
            context,
            chat_id=user_id,
            text=f"✅ درخواست شارژ {amount:,} تومانی ثبت شد.\n⏳ منتظر تایید ادمین بمانید.",
            reply_markup=main_menu(user_id))
        
        admin_text = (
            f"📌 درخواست شارژ جدید\n\n"
            f"👤 کاربر: {update.message.from_user.full_name}\n"
            f"🆔 آیدی: {user_id}\n"
            f"💰 مبلغ: {amount:,} تومان\n"
            f"📅 تاریخ: {get_jalali_date()}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید شارژ", callback_data=f"approve_{user_id}")],
            [InlineKeyboardButton("❌ رد درخواست", callback_data=f"reject_{user_id}")]
        ])
        
        # ارسال به همه ادمین‌ها
        for admin_id in ADMIN_IDS:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=receipt,
                caption=admin_text,
                reply_markup=keyboard
            )
        
        context.user_data.clear()

    elif context.user_data.get("awaiting_product_type"):
        if text.lower() in ["apple", "vpn"]:
            context.user_data["product_type"] = text.lower()
            context.user_data["awaiting_product_type"] = False
            
            if text.lower() == "apple":
                context.user_data["awaiting_product_desc"] = True
                await safe_send_message(context, user_id, "📝 لطفاً توضیحات محصول را وارد کنید:")
            elif text.lower() == "vpn":
                context.user_data["awaiting_vpn_price"] = True
                await safe_send_message(context, user_id, "💵 لطفاً قیمت VPN را به تومان وارد کنید:")
        else:
            await safe_send_message(context, user_id, "⚠️ لطفاً فقط 'apple' یا 'vpn' وارد کنید!")

    elif context.user_data.get("awaiting_vpn_price"):
        try:
            price = int(text)
            if price <= 0:
                await safe_send_message(context, user_id, "⚠️ قیمت باید بیشتر از صفر باشد!")
                return
                
            context.user_data["price"] = price
            context.user_data["awaiting_vpn_price"] = False
            context.user_data["awaiting_vpn_link"] = True
            await safe_send_message(context, user_id, "🔗 لطفاً لینک VPN را وارد کنید:")
        except ValueError:
            await safe_send_message(context, user_id, "⚠️ لطفاً فقط عدد وارد کنید!")

    elif context.user_data.get("awaiting_vpn_link"):
        vpn_link = text
        product_type = context.user_data["product_type"]
        price = context.user_data["price"]
        
        product_id = random.randint(10000, 99999)
        products["vpn"].append({
            "id": product_id,
            "price": price,
            "link": vpn_link
        })
        
        await safe_send_message(
            context,
            chat_id=user_id,
            text=f"✅ محصول VPN با موفقیت اضافه شد!\n\n"
            f"🆔 کد محصول: {product_id}\n"
            f"🔗 لینک: {vpn_link}\n"
            f"💰 قیمت: {price:,} تومان\n"
            f"📝 توضیحات: این VPN یک ماهه با 20 گیگابایت حجم است",
            reply_markup=main_menu(user_id))
        
        context.user_data.clear()

    elif context.user_data.get("awaiting_product_desc"):
        product_type = context.user_data["product_type"]
        product_desc = text
        
        context.user_data["product_desc"] = product_desc
        context.user_data["awaiting_product_desc"] = False
        context.user_data["awaiting_product_price"] = True
        await safe_send_message(context, user_id, "💵 لطفاً قیمت محصول را به تومان وارد کنید:")

    elif context.user_data.get("awaiting_product_price"):
        try:
            price = int(text)
            if price <= 0:
                await safe_send_message(context, user_id, "⚠️ قیمت باید بیشتر از صفر باشد!")
                return
                
            product_id = random.randint(10000, 99999)
            product_type = context.user_data["product_type"]
            products[product_type].append({
                "id": product_id,
                "description": context.user_data["product_desc"],
                "price": price
            })
            
            await safe_send_message(
                context,
                chat_id=user_id,
                text=f"✅ محصول با موفقیت اضافه شد!\n\n"
                f"📦 نوع: {product_type}\n"
                f"🆔 کد محصول: {product_id}\n"
                f"💰 قیمت: {price:,} تومان",
                reply_markup=main_menu(user_id))
            
            context.user_data.clear()
        except ValueError:
            await safe_send_message(context, user_id, "⚠️ لطفاً فقط عدد وارد کنید!")

    elif context.user_data.get("awaiting_user_id"):
        try:
            target_user_id = int(text)
            if target_user_id not in user_data:
                await safe_send_message(
                    context,
                    chat_id=user_id,
                    text="❌ کاربر یافت نشد!",
                    reply_markup=manage_users_menu()
                )
                return
                
            await show_user_info(update, target_user_id, context)
            context.user_data.clear()
        except ValueError:
            await safe_send_message(
                context,
                chat_id=user_id,
                text="⚠️ لطفاً فقط عدد (آیدی کاربر) وارد کنید!",
                reply_markup=manage_users_menu()
            )
    elif context.user_data.get("awaiting_service_info"):
        current_step = context.user_data.get("current_step", 1)
        
        if current_step == 1:  # دریافت ایمیل اپل آیدی
            if not "@" in text or "." not in text:
                await update.message.reply_text("⚠️ لطفاً یک ایمیل معتبر وارد کنید:")
                return
                
            context.user_data["apple_email"] = text
            context.user_data["current_step"] = 2
            await update.message.reply_text("✅ ایمیل دریافت شد.\nلطفاً پسورد ایمیل را ارسال کنید:")
            
        elif current_step == 2:  # دریافت پسورد ایمیل
            context.user_data["apple_password"] = text
            context.user_data["current_step"] = 3
            await update.message.reply_text("✅ پسورد دریافت شد.\nلطفاً عکس واضح از پشت جعبه دستگاه را ارسال کنید:")
            
        elif current_step == 3 and update.message.photo:  # دریافت عکس پشت جعبه
            context.user_data["box_photo"] = update.message.photo[-1].file_id
            context.user_data["current_step"] = 4
            await update.message.reply_text("✅ عکس دریافت شد.\nلطفاً اسکرین شات از صفحه iCloud گوشی را ارسال کنید:")
            
        elif current_step == 4 and (update.message.photo or update.message.document):  # دریافت اسکرین شات iCloud
            file_id = update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id
            context.user_data["icloud_screenshot"] = file_id
            context.user_data["current_step"] = 5
            await update.message.reply_text("✅ اسکرین شات دریافت شد.\nلطفاً اسکرین شات از صفحه About دستگاه را ارسال کنید:")
            
        elif current_step == 5 and (update.message.photo or update.message.document):  # دریافت اسکرین شات About
            file_id = update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id
            context.user_data["about_screenshot"] = file_id
            context.user_data["current_step"] = 6
            await update.message.reply_text("✅ اسکرین شات دریافت شد.\nلطفاً اسکرین شات از شماره سریال دستگاه را ارسال کنید:")
            
        elif current_step == 6 and (update.message.photo or update.message.document):  # دریافت اسکرین شات شماره سریال
            file_id = update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id
            context.user_data["serial_screenshot"] = file_id
            
            # جمع‌آوری تمام اطلاعات
            service_data = {
                "apple_email": context.user_data["apple_email"],
                "apple_password": context.user_data["apple_password"],
                "box_photo": context.user_data["box_photo"],
                "icloud_screenshot": context.user_data["icloud_screenshot"],
                "about_screenshot": context.user_data["about_screenshot"],
                "serial_screenshot": context.user_data["serial_screenshot"],
                "date": get_jalali_date()
            }
            
            context.user_data["service_data"] = service_data
            
            # نمایش اطلاعات جمع‌آوری شده برای تایید
            confirm_message = (
                "🔍 اطلاعات جمع‌آوری شده:\n\n"
                f"📧 ایمیل اپل آیدی: {service_data['apple_email']}\n"
                f"🔑 پسورد ایمیل: {service_data['apple_password']}\n\n"
                "📌 تصاویر ارسال شده:\n"
                "- عکس پشت جعبه\n"
                "- اسکرین شات iCloud\n"
                "- اسکرین شات About\n"
                "- اسکرین شات شماره سریال\n\n"
                "⚠️ نکات مهم:\n"
                "- جیمیل باید در دسترس باشد\n"
                "- مدت زمان فرایند 20 روز کاری میباشد\n"
                "- هزینه فرایند حدود 6 میلیون تومان میباشد\n"
                "- در صورت عدم موفقیت، مبلغ بازگشت داده خواهد شد\n\n"
                "آیا از صحت اطلاعات اطمینان دارید؟"
            )
            
            await update.message.reply_text(
                confirm_message,
                reply_markup=confirm_service_menu()
            )
    elif context.user_data.get("awaiting_discount_user_id"):
        try:
            target_user_id = int(text)
            if target_user_id not in user_data:
                await safe_send_message(
                    context,
                    chat_id=user_id,
                    text="❌ کاربر یافت نشد!",
                    reply_markup=manage_discounts_menu()
                )
                return
                
            context.user_data["target_user_id"] = target_user_id
            context.user_data["awaiting_discount_user_id"] = False
            context.user_data["awaiting_discount_type"] = True
            
            await safe_send_message(
                context,
                chat_id=user_id,
                text="📝 لطفاً نوع تخفیف را انتخاب کنید (apple یا vpn):",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🍏 اپل‌آیدی", callback_data="discount_type_apple"),
                     InlineKeyboardButton("🔒 VPN", callback_data="discount_type_vpn")],
                    [InlineKeyboardButton("◀️ بازگشت", callback_data="manage_discounts")]
                ])
            )
        except ValueError:
            await safe_send_message(
                context,
                chat_id=user_id,
                text="⚠️ لطفاً فقط عدد (آیدی کاربر) وارد کنید!",
                reply_markup=manage_discounts_menu()
            )
    elif context.user_data.get("awaiting_discount_percent"):
        try:
            discount_percent = int(text)
            if discount_percent < 1 or discount_percent > 100:
                await safe_send_message(
                    context,
                    chat_id=user_id,
                    text="⚠️ درصد تخفیف باید بین 1 تا 100 باشد!",
                    reply_markup=manage_discounts_menu()
                )
                return
                
            target_user_id = context.user_data["target_user_id"]
            discount_type = context.user_data["discount_type"]
            
            if target_user_id not in user_discounts:
                user_discounts[target_user_id] = {}
            
            user_discounts[target_user_id][discount_type] = discount_percent
            
            await safe_send_message(
                context,
                chat_id=user_id,
                text=f"✅ تخفیف {discount_percent}% برای {discount_type} کاربر با آیدی {target_user_id} ثبت شد!",
                reply_markup=manage_discounts_menu()
            )
            
            context.user_data.clear()
        except ValueError:
            await safe_send_message(
                context,
                chat_id=user_id,
                text="⚠️ لطفاً فقط عدد (درصد تخفیف) وارد کنید!",
                reply_markup=manage_discounts_menu()
            )

async def approve_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید درخواست شارژ توسط ادمین"""
    query = update.callback_query
    if query:
        await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
        await query.answer("⛔ دسترسی ندارید!")
        return
    
    user_id = int(query.data.split("_")[1])
    if user_id not in pending_charges:
        await query.edit_message_caption("⚠️ این درخواست قبلاً پردازش شده است!")
        return
    
    amount = pending_charges[user_id]["amount"]
    user_wallets[user_id] = user_wallets.get(user_id, 0) + amount
    del pending_charges[user_id]
    
    await query.edit_message_caption(f"✅ شارژ {amount:,} تومانی تایید شد.\n📅 تاریخ: {get_jalali_date()}")
    
    await safe_send_message(
        context,
        chat_id=user_id,
        text=f"🎉 کیف پول شما با مبلغ {amount:,} تومان شارژ شد!\n💰 موجودی جدید: {user_wallets[user_id]:,} تومان\n📅 تاریخ: {get_jalali_date()}",
        reply_markup=main_menu(user_id))

async def reject_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رد درخواست شارژ توسط ادمین"""
    query = update.callback_query
    if query:
        await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
        await query.answer("⛔ دسترسی ندارید!")
        return
 
    user_id = int(query.data.split("_")[1])
    if user_id in pending_charges:
        amount = pending_charges[user_id]["amount"]
        del pending_charges[user_id]
        await query.edit_message_caption(f"❌ درخواست شارژ {amount:,} تومانی رد شد.\n📅 تاریخ: {get_jalali_date()}")
        await safe_send_message(
            context,
            chat_id=user_id,
            text=f"⚠️ درخواست شارژ شما توسط ادمین رد شد.\n📅 تاریخ: {get_jalali_date()}",
            reply_markup=main_menu(user_id))

async def handle_discount_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت انتخاب نوع تخفیف"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:  # بررسی برای همه ادمین‌ها
        await query.answer("⛔ دسترسی ندارید!")
        return
    
    discount_type = query.data.split("_")[2]
    context.user_data["discount_type"] = discount_type
    context.user_data["awaiting_discount_type"] = False
    context.user_data["awaiting_discount_percent"] = True
    
    await safe_edit_message(
        query,
        "📝 لطفاً درصد تخفیف را وارد کنید (1-100):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ بازگشت", callback_data="add_discount")]
        ])
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت خطاهای ربات"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    if update and hasattr(update, 'callback_query') and update.callback_query:
        try:
            await update.callback_query.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except:
            pass
    elif update and update.message:
        try:
            await safe_send_message(
                context,
                chat_id=update.effective_user.id,
                text="⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید."
            )
        except:
            pass

def main():
    """تابع اصلی برای راه‌اندازی ربات"""
    app = Application.builder().token(TOKEN).build()
    
    # دستورات
    app.add_handler(CommandHandler("start", start))
    
    # مدیریت دکمه‌های خاص
    app.add_handler(CallbackQueryHandler(approve_charge, pattern=r"^approve_\d+$"))
    app.add_handler(CallbackQueryHandler(reject_charge, pattern=r"^reject_\d+$"))
    app.add_handler(CallbackQueryHandler(check_membership, pattern=r"^check_membership$"))
    app.add_handler(CallbackQueryHandler(handle_users_list, pattern="^users_list$"))
    app.add_handler(CallbackQueryHandler(handle_discount_type, pattern=r"^discount_type_(apple|vpn)$"))
    app.add_handler(CallbackQueryHandler(handle_remove_specific_discount, pattern=r"^remove_discount_\d+$"))
    
    # مدیریت دکمه‌های عمومی
    app.add_handler(CallbackQueryHandler(handle_buttons))
    
    # مدیریت پیام‌ها
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_message))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    # مدیریت خطاها
    app.add_error_handler(error_handler)
    
    app.run_polling()

if __name__ == "__main__":
    main()