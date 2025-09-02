import telebot
import json
from telebot import types
import schedule
import time
import threading
import emoji
import sqlite3
import random
from datetime import datetime


# === Логування ===
def log(user_id, message):
    log_text = f"[{datetime.now().strftime("%H:%M %d.%m.%Y")}]\t{message}\n"
    log_path = f"logs\\{user_id}.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_text)

def log_sys(message):
    log("system", message)

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
    log_sys('Config.json read to config')

szBotToken = config["botToken"]
bot = telebot.TeleBot(szBotToken)

scheduler_running = True

currArt = ""
currOrderCode = ""
tempOrder = {
    "customerID": "",
    "date": "",
    "ifSended": False,
    "TTN": "",
    "orderTovarList": []
}
tempUser = {
    "id":0,
    "PIB":"",
    "phone":"",
    "address":""
}
# ================ SUPPORT FUNCTION ================
def fetch_as_dicts(query, params=()):
    log_sys(f"Initiating connection to database( {config["pathToDatabase"]} )")
    with sqlite3.connect(config['pathToDatabase']) as conn:
        log_sys("Successfully connected to database")
        cur = conn.cursor()
        cur.execute(query, params)
        columns = [desc[0] for desc in cur.description]
        log_sys("Data was successfully fetched")
        return [dict(zip(columns, row)) for row in cur.fetchall()]

def SQLmake(query, params=()):
    log_sys(f"Initiating connection to database( {config["pathToDatabase"]} )")
    with sqlite3.connect(config['pathToDatabase']) as conn:
        log_sys("Successfully connected to database")
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.lastrowid

def has_emoji(text: str) -> bool:
    return any(char in emoji.EMOJI_DATA for char in text)

def isInt(a):
    try:
        int(a)
        return True
    except ValueError:
        return False

def ifThisCorrectTovar(message):
    global currArt, tempOrder

    log(message.from_user.id, "ifThisCorrectTovar called")

    if message.text in ["/start", "🏠️️На головну"]:
        log(message.from_user.id, '"To main page" button pressed or "/start" command used')
        tempOrder = {
            "customerID": "",
            "date": "",
            "ifSended": False,
            "TTN": "",
            "orderTovarList": []
        }
        start(message)
        return

    found = False

    if message.caption:
        log(message.from_user.id, 'Forwarded message detected. Checking if the message is correct')
        if message.caption.startswith("🔥"):
            log(message.from_user.id, 'Message is correct. Getting data from forwarded message was started')
            textList = message.caption.split("\n")
            for text in textList:
                if "Арт.: " in text:
                    currArt = text.replace("Арт.: ", "").strip()
                    log(message.from_user.id, f'Current article: {currArt}')
                    log(message.from_user.id, 'Trying getting data from database')
                    try:
                        data = fetch_as_dicts('SELECT * FROM products WHERE art = ?', (currArt,))[0]
                        data_prop = fetch_as_dicts('SELECT * FROM product_properties WHERE art = ?', (currArt,))
                        found = True
                        log(message.from_user.id, 'Data was successfully got')
                    except Exception as e:
                        log(message.from_user.id, f'[ERROR] Can`t find article {currArt} in database: {e}')
                        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                        markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"),
                                   types.KeyboardButton("🏠На головну"))
                        bot.send_message(message.chat.id, "❌ Помилка: отримання даних про цей товар на даний неможлива.",
                                         reply_markup=markup)

                    for i in data_prop:
                        if i["availability"]>0:
                            data["sizeList"].append(i["property"])
                    if len(data_prop) == 0:
                        log(message.from_user.id, 'List product propeties is empty. Running reCheckStatus')
                        reCheckStatus(message)
                        log(message.from_user.id, 'Rerunning current function')
                        ifThisCorrectTovar(message)
                    tempOrder["orderTovarList"].append({"art": currArt, "prop": "", "count": 0})
                    log(message.from_user.id, 'Current article was added to tempOrder')

                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    row = []
                    counter = 0
                    for prop in data["sizeList"]:
                        row.append(types.KeyboardButton(prop))
                        counter += 1
                        if counter % 3 == 0:
                            markup.row(*row)
                            row = []
                    if row:
                        markup.row(*row)
                    log(message.from_user.id, 'Size buttons was created')
                    msg = bot.send_message(message.chat.id, "📏Виберіть розмір", reply_markup=markup)
                    bot.register_next_step_handler(msg, handle_prop_selection)
                    return

    else:
        log(message.from_user.id, 'Forwarded message not detected. Working in default mode')
        currArt = message.text.strip()
        log(message.from_user.id, f'Current article: {currArt}')
        log(message.from_user.id, 'Trying getting data from database')
        try:
            data = fetch_as_dicts('SELECT * FROM products WHERE art = ?', (currArt,))[0]
            data_prop = fetch_as_dicts('SELECT * FROM product_properties WHERE art = ?', (currArt,))
            found = True
            log(message.from_user.id, 'Data was successfully got')
        except Exception as e:
            log(message.from_user.id, f'[ERROR] Can`t find article {currArt} in database: {e}')
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"),
                       types.KeyboardButton("🏠На головну"))
            bot.send_message(message.chat.id, "❌ Помилка: отримання даних про цей товар на даний неможлива.",
                             reply_markup=markup)

    if found:
            data["availabilityForProperties"] = {}
            data["priceForProperties"] = {}
            for i in data_prop:
                if i["availability"]>0:
                    data["availabilityForProperties"][i["property"]] = i["availability"]
                    data["priceForProperties"][i["property"]] = i["price"]
            log(message.from_user.id, 'priceForProperties and availabilityForProperties was created')
            log(message.from_user.id, 'Start forming message')
            szResultMessage = formMessageText(data, message.from_user.id)
            images = []
            log(message.from_user.id, 'Trying to get images')
            try:
                if data.get("frontImage"):
                    images.append(open(data["frontImage"], 'rb'))
                    log(message.from_user.id, 'Front image was opened')
                if data.get("backImage"):
                    images.append(open(data["backImage"], 'rb'))
                    log(message.from_user.id, 'Back image was opened')
            except Exception as e:
                log(message.from_user.id, f'[ERROR] Failed to get image for {currArt}: {e}')

            if images:
                media = []
                for i, img in enumerate(images):
                    if i == 0:
                        if szResultMessage != "NULL":
                            media.append(types.InputMediaPhoto(img, caption=szResultMessage, parse_mode='HTML'))
                        else:
                            log(message.from_user.id, '[ERROR] Can`t send unformed message')
                            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                            markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"),
                                       types.KeyboardButton("🏠На головну"))
                            bot.send_message(message.chat.id, "❌ Помилка: Помилка форматування тексту.",
                                             reply_markup=markup)
                            return
                    else:
                        media.append(types.InputMediaPhoto(img))
                bot.send_media_group(message.chat.id, media)
                log(message.from_user.id, 'Image was sent successfully')
            else:
                bot.send_message(message.chat.id, szResultMessage, parse_mode='HTML')
                log(message.from_user.id, 'Message was sent without images')

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("✅Так"), types.KeyboardButton("❌Ні"))
            msg = bot.send_message(message.chat.id, "Чи це та форма яку ви хочете замовити?", reply_markup=markup)
            bot.register_next_step_handler(msg, handle_tovar_selection)

    if not found:
        log(message.from_user.id, f'[ERROR] Can`t find {currArt} in database')
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"), types.KeyboardButton("🏠На головну"))
        bot.send_message(message.chat.id, "❌ Помилка: Артикул не знайдено.", reply_markup=markup)

def handle_tovar_selection(message):
    global tempOrder, currArt

    log(message.from_user.id, "handle_tovar_selection called")

    if message.text in ["/start", "🏠На головну"]:
        log(message.from_user.id, '"To main page" button pressed or "/start" command used')
        start(message)
        tempOrder = {
            "customerID": "",
            "date": "",
            "ifSended": False,
            "TTN": "",
            "orderTovarList": []
        }
        return

    if message.text == "✅Так":
        log(message.from_user.id, f'Current article: {currArt}')
        log(message.from_user.id, 'Trying getting data from database')
        try:
            product_data = fetch_as_dicts("SELECT art FROM products WHERE art = ?", (currArt,))
            if not product_data:
                log(message.from_user.id, f'[ERROR] Can`t find article {currArt} in database')
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"),
                           types.KeyboardButton("🏠На головну"))
                bot.send_message(message.chat.id, "❌ Помилка: отримання даних про цей товар на даний неможлива.",
                                 reply_markup=markup)
                return
            data = product_data[0]
            log(message.from_user.id, 'Data was successfully got')
            data["availabilityForProperties"] = {}
            log(message.from_user.id, 'Trying tempAvailabilityForProperties from database')
            tempAvailabilityForProperties = fetch_as_dicts(
                "SELECT property, availability as count FROM product_properties WHERE art = ?",
                (currArt,)
            )
            log(message.from_user.id, 'tempAvailabilityForProperties was successfully got')
        except Exception as e:
            log(message.from_user.id, f'[ERROR] Can`t find article {currArt} in database: {e}')
            tempOrder["customerID"] = ""
            tempOrder["date"] = ""
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(
                types.KeyboardButton("✉Зв'язатися з менеджером"),
                types.KeyboardButton("🏠На головну")
            )
            bot.send_message(message.chat.id, "❌ Помилка: Артикул не знайдено.", reply_markup=markup)
            return

        tempOrder["orderTovarList"].append({"art": currArt, "prop": "", "count": 0})
        log(message.from_user.id, 'Current article was added to tempOrder')

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        row = []
        counter = 0

        for prop in tempAvailabilityForProperties:
            property_name = prop['property']
            count = prop['count']
            if count != 0:
                row.append(types.KeyboardButton(property_name))
                counter += 1
                if counter % 3 == 0:
                    markup.row(*row)
                    row = []

        if row:
            markup.row(*row)

        log(message.from_user.id, 'Size buttons was created')
        msg = bot.send_message(message.chat.id, "Виберіть розмір", reply_markup=markup)
        bot.register_next_step_handler(msg, handle_prop_selection)
        return
    else:
        log(message.from_user.id, 'Running rechoosing article function')
        make_order(message)

def handle_prop_selection(message):
    global tempOrder, currArt

    log(message.from_user.id, "handle_prop_selection called")

    if message.text in ["/start", "🏠На головну"]:
        log(message.from_user.id, '"To main page" button pressed or "/start" command used')
        tempOrder = {
            "customerID": "",
            "date": "",
            "ifSended": False,
            "TTN": "",
            "orderTovarList": []
        }
        start(message)
        return

    prop = message.text.strip()
    if not tempOrder["orderTovarList"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"), types.KeyboardButton("🏠На головну"))
        bot.send_message(message.chat.id, "❌ Помилка: Список замовлень порожній.", reply_markup=markup)
        log(message.from_user.id, f'[ERROR] tempOrder["orderTovarList"] is empty')
        return

    lastAddedTovar = tempOrder["orderTovarList"][-1]
    targetArt = lastAddedTovar["art"]
    isAlreadyAdded = False
    currTovar = {}
    currData = {}

    log(message.from_user.id, 'Checking if product is already in orderTovarList')
    for tovar in tempOrder["orderTovarList"]:
        if tovar["art"] == targetArt and tovar["prop"] == prop:
            log(message.from_user.id, f'{targetArt}:{prop} is already in orderTovarList')
            isAlreadyAdded = True
            currTovar = tovar

    log(message.from_user.id, 'Trying getting data from database')
    try:
        currData = fetch_as_dicts("SELECT property, availability FROM product_properties WHERE art = ?", (currArt,))
        log(message.from_user.id, 'Data was successfully got')
        availability_dict = {item['property']: int(item['availability']) for item in currData}
        log(message.from_user.id, 'Availability dictionary was created')
    except Exception:
        log(message.from_user.id, f'[ERROR] Can`t find {currArt} from database')
        availability_dict = {}
        log(message.from_user.id, 'Availability dictionary was deleted')

    if availability_dict:
        available_count = availability_dict.get(prop, 0)

        if prop not in availability_dict:
            log(message.from_user.id, f'[ERROR] Selected property "{prop}" not found in DB for art {currArt}')
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            counter = 0
            row=[]
            for property_name, count in availability_dict.items():
                if count != 0:
                    row.append(types.KeyboardButton(property_name))
                    counter += 1
                    if counter % 3 == 0:
                        markup.row(*row)
                        row = []
            if row:
                markup.row(*row)

            markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"), types.KeyboardButton("🏠На головну"))
            msg = bot.send_message(message.chat.id,
                             f"❌ Помилка: Обраний розмір <b>{prop}</b> не знайдено в базі. Спробуйте ще раз.",
                             parse_mode='HTML', reply_markup=markup)
            bot.register_next_step_handler(msg, handle_prop_selection)
            return
        if isAlreadyAdded:
            if currTovar["count"] + 1 <= available_count:
                currTovar["count"] += 1
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add(types.KeyboardButton("✅Так"), types.KeyboardButton("❌Ні"))
                log(message.from_user.id, f'{targetArt} {prop} count incremented')
                msg = bot.send_message(message.chat.id, f"✅ Додано до замовлення: {targetArt}, розмір {prop}. Додати ще?", reply_markup=markup)
                bot.register_next_step_handler(msg, handle_adding_tovar_to_order)
            else:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add(types.KeyboardButton("✅Так"), types.KeyboardButton("❌Ні"))
                log(message.from_user.id, f'{targetArt} {prop} не доступний у потрібній кількості')
                del tempOrder["orderTovarList"][-1]
                msg = bot.send_message(message.chat.id, f"Товар {targetArt} {prop} відсутній у потрібній кількості. Виберіть інший.", reply_markup=markup)
                bot.register_next_step_handler(msg, handle_adding_tovar_to_order)
        else:
            if available_count > 0:
                lastAddedTovar["prop"] = prop
                lastAddedTovar["count"] = 1
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add(types.KeyboardButton("Додати новий товар➕"), types.KeyboardButton("Продовжити➡"))
                log(message.from_user.id, f'{targetArt} {prop} додано до замовлення')
                msg = bot.send_message(message.chat.id, f"✅ Додано: {targetArt} {prop}. Бажаєте додати ще товар?", reply_markup=markup)
                bot.register_next_step_handler(msg, handle_adding_tovar_to_order)
            else:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"), types.KeyboardButton("🏠На головну"))
                log(message.from_user.id, f'[ERROR] Товар {targetArt} {prop} не доступний')
                bot.send_message(message.chat.id, "❌ Помилка: Вибір не наявного товару.", reply_markup=markup)
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"), types.KeyboardButton("🏠На головну"))
        log(message.from_user.id, f'[ERROR] Can`t find {prop} for {currArt} in database')
        bot.send_message(message.chat.id, "❌ Помилка: Розмір не знайдено.", reply_markup=markup)

def handle_adding_tovar_to_order(message):
    global tempOrder

    log(message.from_user.id, "handle_adding_tovar_to_order called")

    if message.text in ["/start", "🏠На головну"]:
        log(message.from_user.id, '"To main page" button pressed')
        tempOrder = {
            "customerID": "",
            "date": "",
            "ifSended": False,
            "TTN": "",
            "orderTovarList": []
        }
        start(message)
        return

    elif message.text == "Додати новий товар➕":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        row = []
        log(message.from_user.id, 'Trying getting data from database')
        try:
            DataList = fetch_as_dicts("SELECT * FROM products")
            log(message.from_user.id, 'Data was successfully got')
        except Exception as e:
            log(message.from_user.id, f"[ERROR] Failed to fetch products: {e}")
            DataList = []

        for idx, item in enumerate(DataList):
            row.append(types.KeyboardButton(item["art"]))
            if (idx + 1) % 3 == 0:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)

        log(message.from_user.id, 'Articles button was created')
        msgText = (
            "🤔 <b>Оберіть товар</b> за артикулом або просто <b>перешліть</b> повідомлення з нашого каналу 📨\n\n"
            "🆔 Нажміть на кнопку з відповідним артикулом\n\n\t\tабо\n\n"
            "📲 Перешліть повідомлення прямо сюди — і я все оброблю автоматично!"
        )
        msg = bot.send_message(message.chat.id, msgText, reply_markup=markup, parse_mode="HTML")
        bot.register_next_step_handler(msg, ifThisCorrectTovar)

    else:
        log(message.from_user.id, 'Trying getting data from database')
        try:
            user = fetch_as_dicts("SELECT * FROM users WHERE id = ?", (message.from_user.id,))[0]
            log(message.from_user.id, 'Data was successfully got')
            order_code = SQLmake(
                'INSERT INTO orders (customerID, date, ifSended, TTN) VALUES (?, ?, ?, ?)',
                (tempOrder["customerID"], tempOrder["date"], False, "")
            )
            log(message.from_user.id, f'Order data was written to database. Order code - {order_code} was successfully got')
            log(message.from_user.id, 'Trying write orderTovarList to database')
            for i in tempOrder["orderTovarList"]:
                order_code = SQLmake(
                    'INSERT INTO order_items (code, art, prop, count) VALUES (?, ?, ?, ?)',
                    (order_code, i["art"], i["prop"], i["count"]))
                try:
                    SQLmake("UPDATE product_properties SET availability = availability - ?  WHERE art = ?  AND property=?", (i["count"],i["art"], i["prop"]))
                except Exception as e:
                    log(message.from_user.id, f"[ERROR] Failed to update availability for {order_code}: {e}")
            log(message.from_user.id, 'orderTovarList was written to database')

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("🛍️Зробити замовлення"))
            markup.add(types.KeyboardButton("🛒Мої замовлення"))
            markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"))

            szResultMessage = (
                "✅<b>Замовлення відправлено на обробку.</b>\n\n"
                "Щодо відправлення вам напишуть протягом дня.\n\n"
                "<b>💛Дякуємо, що вибрали нас!💛</b>"
            )

            bot.send_message(message.chat.id, szResultMessage, reply_markup=markup, parse_mode='HTML')

            try:
                log(message.from_user.id, 'Trying send notification to manager')
                adminChat = bot.get_chat(config["adminIDs"][0])
                log(message.from_user.id, f"Manager id: {config["adminIDs"][0]}")
                username = bot.get_chat(message.from_user.id).username
                user = fetch_as_dicts("SELECT * FROM users WHERE id = ?", (message.from_user.id,))[0]
                szResultMessage = f'‼НОВЕ ЗАМОВЛЕННЯ ВІД КОРИСТУВАЧА <a href="https://t.me/{username}">{username}</a>‼\n\n'
                szResultMessage += f'''<b>ЗАМОВЛЕННЯ №{order_code}</b>
    📅Дата: {tempOrder["date"]}\n
    🔗Користувач: <a href="https://t.me/{username}">{username}</a>
        🙎‍♂️ПІБ: {user["PIB"]}
        📞Номер телефону: {user["phone"]}
        🏠Адреса: {user["address"]}\n
    📃Список покупок:\n'''
                for tovar in tempOrder["orderTovarList"]:
                    szResultMessage += f'\t\t\t\t\t\t\t\t⚫{tovar["art"]}:{tovar["prop"]} - {tovar["count"]}\n'
                bot.send_message(
                    adminChat.id,
                    szResultMessage,
                    parse_mode='HTML'
                )
                log(message.from_user.id, "Notification was sent to manager")
            except Exception as e:
                adminChat = bot.get_chat(config["adminIDs"][0])
                log(message.from_user.id, f"[ERROR] Can`t send notification about order to manager: {e}")
                bot.send_message(
                    adminChat.id,
                    f"Через помилку не можу відправити сповіщення про нове замовлення. Перепровірте список замовлень. Користувач = {username}",
                    parse_mode='HTML'
                )
            tempOrder = {"customerID": "", "date": "", "ifSended": False, "TTN": "", "orderTovarList": []}
            log(message.from_user.id, "tempOrder reset after saving")
        except Exception as e:
            log(message.from_user.id, f"[ERROR] Failed to save order: {e}")
            msg = bot.send_message(
                message.chat.id,
                "Давайте зберемо ваші дані для відправки. <b>Введіть ваше ПІБ:</b>",
                parse_mode='HTML',
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("🏠На головну"))
            )
            bot.register_next_step_handler(msg, get_PIB)

def get_PIB(message):
    global tempUser, tempOrder
    log(message.from_user.id, "get_PIB called")
    if message.text in ["🏠На головну", "/start"]:
        tempOrder = {"customerID": "", "date": "", "ifSended": False, "TTN": "", "orderTovarList": []}
        tempUser = {"id": 0, "PIB": "", "phone": "", "address": ""}
        back_to_main(message)
        return

    if not has_emoji(message.text):
        tempUser["id"] = message.from_user.id
        tempUser["PIB"] = message.text
        msg = bot.send_message(message.chat.id, "Введіть ваш номер телефону:", parse_mode='HTML')
        bot.register_next_step_handler(msg, get_phone)
    else:
        msg = bot.send_message(message.chat.id, "Введіть ще раз ваше ПІБ без емодзі:", parse_mode='HTML')
        bot.register_next_step_handler(msg, get_PIB)

def get_phone(message):
    global tempUser, tempOrder

    log(message.from_user.id, "get_phone called")
    if message.text in ["🏠На головну", "/start"]:
        log(message.from_user.id, '"To main page" button pressed')
        tempOrder = {"customerID": "", "date": "", "ifSended": False, "TTN": "", "orderTovarList": []}
        tempUser = {"id": 0, "PIB": "", "phone": "", "address": ""}
        back_to_main(message)
        return

    if has_emoji(message.text):
        log(message.from_user.id, '[ERROR] Message with phone number has emoji. Asking to re-enter number')
        msg = bot.send_message(message.chat.id, "Номер телефону введено неправильно. Введіть ваш номер ще раз, будь ласка:", parse_mode='HTML')
        bot.register_next_step_handler(msg, get_phone)
        return

    phone = message.text.strip()
    log(message.from_user.id, 'Phone number was got')
    valid = False

    if len(phone) == 10 and phone.startswith("0") and isInt(phone):
        tempUser["phone"] = f"+38{phone}"
        valid = True
    elif len(phone) == 13 and phone.startswith("+") and isInt(phone[1:]):
        tempUser["phone"] = phone
        valid = True
    elif len(phone) == 12 and phone.startswith("3") and isInt(phone):
        tempUser["phone"] = f"+{phone}"
        valid = True

    if valid:
        log(message.from_user.id, 'Phone number was succssefully read')
        msg = bot.send_message(message.chat.id, "Введіть адресу відділення:", parse_mode='HTML')
        bot.register_next_step_handler(msg, submit_data_colect)
    else:
        log(message.from_user.id, '[ERROR] Phonr number is not valid. Asking to re-enter number')
        msg = bot.send_message(message.chat.id, "Номер телефону введено неправильно. Спробуйте ще раз:", parse_mode='HTML')
        bot.register_next_step_handler(msg, get_phone)

def submit_data_colect(message):
    global tempUser, tempOrder
    user_id = message.from_user.id
    log(user_id, "submit_data_colect called")

    if message.text == "🏠На головну":
        log(user_id, '"To main page" button pressed')
        tempOrder = {"customerID": "", "date": "", "ifSended": False, "TTN": "", "orderTovarList": []}
        tempUser = {"id": 0, "PIB": "", "phone": "", "address": ""}
        log(user_id, "tempOrder and tempUser reset due to 'main page' command")
        back_to_main(message)
        return

    if not has_emoji(message.text):
        tempUser["address"] = message.text
        log(user_id, f"Address received: {message.text}")

        try:
            log(user_id, "Attempting to insert user into database")
            SQLmake(
                'INSERT INTO users (id, PIB, phone, address) VALUES (?, ?, ?, ?)',
                (tempUser["id"], tempUser["PIB"], tempUser["phone"], tempUser["address"])
            )
            log(user_id, "User successfully inserted into database")
        except Exception as e:
            log(user_id, f"[ERROR] Failed to insert user: {e}")

        try:
            log(user_id, "Attempting to insert order into database")
            order_code = SQLmake(
                'INSERT INTO orders (customerID, date, ifSended, TTN) VALUES (?, ?, ?, ?)',
                (tempOrder["customerID"], tempOrder["date"], False, "")
            )
            log(user_id, f"Order successfully inserted with code {order_code}")

            for i in tempOrder["orderTovarList"]:
                log(user_id, f"Inserting order item: art={i['art']}, prop={i['prop']}, count={i['count']}")
                order_code = SQLmake(
                    'INSERT INTO order_items (code, art, prop, count) VALUES (?, ?, ?, ?)',
                    (order_code, i["art"], i["prop"], i["count"])
                )
                try:
                    SQLmake("UPDATE product_properties SET availability = availability - ?  WHERE art = ?  AND property=?", (i["count"],i["art"], i["prop"]))
                except Exception as e:
                    log(message.from_user.id, f"[ERROR] Failed to update availability for {order_code}: {e}")
            log(user_id, "All order items successfully inserted")

        except Exception as e:
            log(user_id, f"[ERROR] Failed to insert order or items: {e}")

        szResultMessage = (
            "✅<b>Ваше замовлення відправлено на обробку.</b>\n\n"
            "Ми зв'яжемося з вами щодо доставки протягом дня.\n\n"
            "<b>💛Дякуємо, що вибрали нас!💛</b>"
        )

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("🛍️Зробити замовлення"))
        markup.add(types.KeyboardButton("🛒Мої замовлення"))
        markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"))
        log(user_id, "Sending confirmation message and resetting menu buttons")
        bot.send_message(message.chat.id, szResultMessage, parse_mode='HTML', reply_markup=markup)

        try:
            log(message.from_user.id, 'Trying send notification to manager')
            adminChat = bot.get_chat(config["adminIDs"][0])
            log(message.from_user.id, f"Manager id: {config["adminIDs"][0]}")
            username = bot.get_chat(message.from_user.id).username
            szResultMessage = f'‼НОВЕ ЗАМОВЛЕННЯ ВІД КОРИСТУВАЧА <a href="https://t.me/{username}">{username}</a>‼\n'
            szResultMessage += f'''<b>ЗАМОВЛЕННЯ №{order_code}</b>
    📅Дата: {tempOrder["date"]}\n
    🔗Користувач: <a href="https://t.me/{username}">{username}</a>
        🙎‍♂️ПІБ: {tempUser["PIB"]}
        📞Номер телефону: {tempUser["phone"]}
        🏠Адреса: {tempUser["address"]}\n
    📃Список покупок:\n'''
            for tovar in tempOrder["orderTovarList"]:
                szResultMessage += f'\t\t\t\t\t\t\t\t⚫{tovar["art"]}:{tovar["prop"]} - {tovar["count"]}\n'
            bot.send_message(
                    adminChat.id,
                    szResultMessage,
                    parse_mode='HTML'
            )
            log(message.from_user.id, "Notification was sent to manager")
        except Exception as e:
            adminChat = bot.get_chat(config["adminIDs"][0])
            bot.send_message(
            adminChat.id,
            f"Через помилку не можу відправити сповіщення про нове замовлення. Перепровірте список замовлень. Користувач = {username}",
            parse_mode='HTML'
        )
        tempOrder = {"customerID": "", "date": "", "ifSended": False, "TTN": "", "orderTovarList": []}
        tempUser = {"id": 0, "PIB": "", "phone": "", "address": ""}
        log(user_id, "tempOrder and tempUser reset after saving")
    else:
        log(user_id, f"[ERROR] Address contains emoji: {message.text}")
        msg = bot.send_message(message.chat.id, "Будь ласка, введіть адресу ще раз без емодзі:", parse_mode='HTML')
        log(user_id, "Asking user to re-enter address without emoji")
        bot.register_next_step_handler(msg, submit_data_colect)

# ================ USER MESSAGE HANDLERS ================
@bot.message_handler(commands=['start'])
def start(message):
    try:
        log(message.from_user.id, '"/start" command received')
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("🛍️Зробити замовлення"))
        markup.add(types.KeyboardButton("🛒Мої замовлення"))
        markup.add(types.KeyboardButton("✉Зв'язатися з менеджером"))
        log(message.from_user.id, "Main menu buttons created")
        bot.send_message(message.chat.id, "👋Вітаємо! Оберіть опцію:", reply_markup=markup)
        log(message.from_user.id, "Main menu message sent")
    except Exception as e:
        log(message.from_user.id, f"[ERROR] start(): {e}")


@bot.message_handler(func=lambda message: message.text == "🛒Мої замовлення")
def my_orders(message):
    try:
        log(message.from_user.id, '"My orders" button pressed')
        orderList = fetch_as_dicts("SELECT * FROM orders WHERE customerID = ?", (int(message.from_user.id),))
        log(message.from_user.id, f"{len(orderList)} orders fetched from database")
        if orderList:
            szResultMessage = f'\t<b>🧾 МОЇ ЗАМОВЛЕННЯ</b>\n'
            for order in orderList:
                log(message.from_user.id, f"Processing order #{order['code']}")
                szResultMessage += f'''
<b>📦 Замовлення №{order["code"]}</b>
    📅 <b>Дата:</b> {order["date"]}
    📩 <b>Відправлено:</b> {"✅ Так" if order["ifSended"] else "❌ Ні"}
        🔢 <b>ТТН:</b> {order["TTN"]}
    🛍️ <b>Список покупок:</b>\n'''
                orderTovarList = fetch_as_dicts("SELECT * FROM order_items WHERE code = ?", (int(order["code"]),))
                log(message.from_user.id, f"{len(orderTovarList)} items found for order #{order['code']}")
                for tovar in orderTovarList:
                    szResultMessage += f'\t\t\t\t\t\t •🛒 <b>{tovar["art"]}</b>: {tovar["prop"]} — {tovar["count"]} шт.\n'
            bot.send_message(message.chat.id, szResultMessage, parse_mode='HTML')
            log(message.from_user.id, "Order list sent to user")
        else:
            log(message.from_user.id, f"User has no orders")
            bot.send_message(message.chat.id, "Наразі у вас відсутні замовлення", parse_mode='HTML')
    except Exception as e:
        log(message.from_user.id, f"[ERROR] my_orders(): {e}")
        bot.send_message(message.chat.id, "Наразі у вас відсутні замовлення", parse_mode='HTML')


@bot.message_handler(func=lambda message: message.text == "🛍️Зробити замовлення")
def make_order(message):
    try:
        global tempOrder
        log(message.from_user.id, '"Make order" button pressed')

        tempOrder = {
            "customerID": message.from_user.id,
            "date": datetime.now().strftime("%H:%M %d.%m.%Y"),
            "ifSended": False,
            "TTN": "",
            "orderTovarList": []
        }
        log(message.from_user.id, f'tempOrder initialized: {tempOrder}')

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        row = []
        DataList = fetch_as_dicts("SELECT * FROM products")
        log(message.from_user.id, f"{len(DataList)} products loaded from database")

        for idx, item in enumerate(DataList):
            row.append(types.KeyboardButton(item["art"]))
            if (idx + 1) % 3 == 0:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)
        log(message.from_user.id, "Product buttons added to markup")

        msgText = (
            "🤔 <b>Оберіть товар</b> за артикулом або просто <b>перешліть</b> повідомлення з нашого каналу 📨\n\n"
            "🆔 Нажміть на кнопку з відповідним артикулом\n\n\t\tабо\n\n"
            "📲 Перешліть повідомлення прямо сюди — і я все оброблю автоматично!"
        )
        msg = bot.send_message(message.chat.id, msgText, reply_markup=markup, parse_mode='HTML')
        log(message.from_user.id, "Product selection message sent")
        bot.register_next_step_handler(msg, ifThisCorrectTovar)
        log(message.from_user.id, "Next step handler registered for product selection")
    except Exception as e:
        log(message.from_user.id, f"[ERROR] make_order(): {e}")
        bot.send_message(message.chat.id, "⚠ Сталася помилка при початку оформлення замовлення")


@bot.message_handler(func=lambda message: message.text == "✉Зв'язатися з менеджером")
def contact_to_manager(message):
    try:
        log(message.from_user.id, '"Contact to manager" button pressed')
        adminChat = bot.get_chat(config["adminIDs"][0])
        username = bot.get_chat(message.from_user.id).username
        log(message.from_user.id, f"User username resolved: {username}")

        bot.send_message(
            adminChat.id,
            f'‼‼Запит на зворотній зв\'язок з користувачем <a href="https://t.me/{username}">{username}</a>‼‼',
            parse_mode='HTML'
        )
        log(message.from_user.id, "Contact request sent to admin")

        msg = (
            "🧾 <b>Ваше звернення прийнято!</b>\n\n"
            "Наш менеджер звʼяжеться з вами найближчим часом для уточнення деталей.\n"
            "Якщо у вас є додаткові питання — не соромтеся написати напряму.\n\n"
            f"📞 <b>Контакт менеджера:</b> 🧓 <a href=\"tg://user?id={config['adminIDs'][0]}\">Менеджер</a>\n\n"
            "📦 Дякуємо, що обрали нас! Ми завжди готові допомогти 🤝"
        )
        bot.send_message(message.chat.id, msg, parse_mode='HTML')
        log(message.from_user.id, "Confirmation message sent to user")
    except Exception as e:
        log(message.from_user.id, f"[ERROR] contact_to_manager(): {e}")
        bot.send_message(message.chat.id, "⚠ Не вдалося звʼязатися з менеджером")


@bot.message_handler(func=lambda message: message.text == "🏠На головну")
def back_to_main(message):
    try:
        log(message.from_user.id, '"To main page" button pressed')
        start(message)
        log(message.from_user.id, "start() called from back_to_main")
    except Exception as e:
        log(message.from_user.id, f"[ERROR] back_to_main(): {e}")
        bot.send_message(message.chat.id, "⚠ Не вдалося повернутись на головну сторінку")



# ================ ADMIN COMMANDS ================
@bot.message_handler(commands=['start_sending'])
def start_sending(message):
    global scheduler_running
    if message.from_user.id in config["adminIDs"]:
        scheduler_running = True
        log_sys('Scheduler started by admin')
        log(message.from_user.id, 'Command /start_sending used')
        bot.send_message(message.chat.id, "Розсилка запущена🏃‍♀️")

@bot.message_handler(commands=['stop_sending'])
def stop_sending(message):
    global scheduler_running
    if message.from_user.id in config["adminIDs"]:
        scheduler_running = False
        log_sys('Scheduler stopped by admin')
        log(message.from_user.id, 'Command /stop_sending used')
        bot.send_message(message.chat.id, "Розсилка зупинена⛔")


@bot.message_handler(commands=['orderlist'])
def send_orderlist1(message):
    if message.from_user.id in config["adminIDs"]:
        log(message.from_user.id, 'Command /orderlist used')
        szResultMessage = "📃Список замовлень:\n"
        try:
            orderList = fetch_as_dicts("SELECT * FROM orders")
            log(message.from_user.id, f'{len(orderList)} orders fetched from database')
        except Exception as e:
            orderList = []
            log(message.from_user.id, f'[ERROR] Failed to fetch orders: {e}')

        if orderList:
            for order in orderList:
                try:
                    username = bot.get_chat(order["customerID"]).username
                except:
                    username = "Unknown"
                ifSended = "Відправлено✅" if order["ifSended"] else "НЕ відправлено❌"
                szResultMessage += f'{order["code"]}. <a href="tg://user?id={order["customerID"]}">{username}</a> : {ifSended}\n'

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            row = []
            for idx, order in enumerate(orderList):
                row.append(types.KeyboardButton(order["code"]))
                if (idx + 1) % 3 == 0:
                    markup.row(*row)
                    row = []
            if row:
                markup.row(*row)
            log(message.from_user.id, 'Order list buttons generated')
            msg = bot.send_message(message.chat.id, szResultMessage, parse_mode='HTML', reply_markup=markup)
            log(message.from_user.id, 'Order list message sent')
            bot.register_next_step_handler(msg, send_orderlist2)
        else:
            log(message.from_user.id, 'No orders found')
            bot.send_message(message.chat.id, "Наразі нема замовлень", parse_mode='HTML')


def send_orderlist2(message):
    global currOrderCode
    if message.text in ["/start", "🏠На головну"]:
        log(message.from_user.id, '"To main page" button pressed')
        start(message)
        return
    try:
        log(message.from_user.id, f'Requested order #{message.text}')
        order = fetch_as_dicts(f"SELECT * FROM orders WHERE code = {int(message.text)}")[0]
        order["orderTovarList"] = fetch_as_dicts(f"SELECT * FROM order_items WHERE code = {int(order['code'])}")
        currOrderCode = int(order['code'])
        log(message.from_user.id, f'Order #{currOrderCode} details loaded')

        currUser = fetch_as_dicts(f"SELECT * FROM users WHERE id = {order['customerID']}")[0]
        username = bot.get_chat(order["customerID"]).username

        szResultMessage = f'''\t<b>ЗАМОВЛЕННЯ №{order["code"]}</b>
📅Дата: {order["date"]}\n
🔗Користувач: <a href="tg://user?id={order["customerID"]}">{username}</a>
    🙎‍♂️ПІБ: {currUser["PIB"]}
    📞Номер телефону: {currUser["phone"]}
    🏠Адреса: {currUser["address"]}\n
🔢ТТН: {order["TTN"]}
📩Відправлено: {"Так" if order["ifSended"] else "Ні"}\n
📃Список покупок:\n'''
        for tovar in order["orderTovarList"]:
            szResultMessage += f'\t\t⚫{tovar["art"]}:{tovar["prop"]} - {tovar["count"]}\n'

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if order["ifSended"]:
            markup.add(types.KeyboardButton("Змінити ТТН"))
        else:
            markup.add(types.KeyboardButton("Додати ТТН"))
        markup.add(types.KeyboardButton("⬅Назад"))

        msg = bot.send_message(message.chat.id, szResultMessage, parse_mode='HTML', reply_markup=markup)
        log(message.from_user.id, f'Detailed order #{currOrderCode} message sent')
        bot.register_next_step_handler(msg, send_orderlist3)
    except Exception as e:
        log(message.from_user.id, f'[ERROR] Failed in send_orderlist2: {e}')


def send_orderlist3(message):
    global currOrderCode
    if message.text == "⬅Назад":
        log(message.from_user.id, 'Back button pressed in order detail view')
        send_orderlist1(message)
    elif message.text in ["/start", "🏠На головну"]:
        log(message.from_user.id, '"To main page" button pressed')
        start(message)
        return
    elif message.text in ["Додати ТТН", "Змінити ТТН"]:
        log(message.from_user.id, 'Requesting TTN input')
        msg = bot.send_message(message.chat.id, "🔢Введіть ТТН", parse_mode='HTML')
        bot.register_next_step_handler(msg, add_TTN)



def add_TTN(message):
    if message.text in ["/start", "🏠На головну"]:
        log(message.from_user.id, '"To main page" button pressed')
        start(message)
        return
    try:
        log(message.from_user.id, f'Updating TTN for order #{currOrderCode} to "{message.text}"')
        SQLmake("UPDATE orders SET TTN = ?, ifSended = ? WHERE code = ?", (message.text, 1, currOrderCode))
        log(message.from_user.id, f'TTN updated successfully for order #{currOrderCode}')
        send_orderlist1(message)
    except Exception as e:
        log(message.from_user.id, f'[ERROR] Failed to update TTN: {e}')


@bot.message_handler(commands=['recheckstatus'])
def reCheckStatus(message):
    try:
        log(message.from_user.id, 'Command /recheckstatus used')
        DataList = fetch_as_dicts("SELECT code, frontImage, backImage FROM orders")
        log(message.from_user.id, f'{len(DataList)} orders fetched for status recheck')

        for data in DataList:
            if len(data["frontImage"]) < 2 and len(data["backImage"]) < 2:
                SQLmake("UPDATE orders SET active = 0 WHERE code = ?", (data['code'],))
                log(message.from_user.id, f'Order #{data["code"]} marked inactive')
            else:
                SQLmake("UPDATE orders SET active = 1 WHERE code = ?", (data['code'],))
                log(message.from_user.id, f'Order #{data["code"]} marked active')
        bot.send_message(message.chat.id, "Статуси товарів були повторно перевірені")
        log(message.from_user.id, 'Order statuses rechecked and message sent')
    except Exception as e:
        log_sys(f"[ERROR] Failed in reCheckStatus: {e}")

# ================ SCHEDULER ================

def formMessageText(data, user_id):
    try:
        name = data.get('name', '⚽ Форма')
        art = data.get('art', '---')
        log(user_id, f'Start forming message for article: {art}')

        about = data.get('about', '').strip()
        if not about:
            log(user_id, f'Description not found for {art}, auto-generating')
            if "форма" in name.lower():
                brand = ""
                player = ""
                for word in ["ronaldo","messi", "mbappe", "mudryk", "dovbyk"]:
                    if word in name.lower():
                        player = word.capitalize()
                for word in ["nike", "adidas", "puma", "select", "umbro"]:
                    if word in name.lower():
                        brand = word.capitalize()
                if brand and player:
                    abouts = [f"👕 Дитяча футбольна форма {brand} {player} — комплект з футболки та шортів у стилі {player}.\n\t• Дихаюча тканина\n\t• Принт “{player}”\n\t• Підходить для тренувань, ігор і повсякденного носіння\nРекомендована для дітей віком 5–16 років.",
                        f"⚽️ Комплект дитячої форми {brand} {player} — ідеальний вибір для активних дітей.\n\t• Високоякісний поліестер, приємний до тіла\n\t• Яскравий дизайн у стилі {player}\n\t• Футболка + шорти, еластичний пояс\nФорма не сковує рухів і легко переться.",
                        f"📦 У комплекті: футболка та шорти {brand} {player}\n\t• Стильна репліка з іменем та номером легендарного гравця\n\t• Виготовлена з легкого, дихаючого матеріалу\n\t• Добре підходить для футбольних секцій і гри на вулиці\nДоступна в різних розмірах для дітей різного віку."]
                elif brand:
                    abouts = [f"👕 Дитяча футбольна форма {brand} — комплект з футболки та шортів.\n\t• Дихаюча тканина\n\t• Підходить для тренувань, ігор і повсякденного носіння\nРекомендована для дітей віком 5–16 років.",
                         f"⚽️ Комплект дитячої форми {brand} — ідеальний вибір для активних дітей.\n\t• Високоякісний поліестер, приємний до тіла\n\t• Футболка + шорти, еластичний пояс\nФорма не сковує рухів і легко переться.",
                         f"📦 У комплекті: футболка та шорти {brand}\n\t• Стильна репліка з іменем та номером легендарного гравця\n\t• Виготовлена з легкого, дихаючого матеріалу\n\t• Добре підходить для футбольних секцій і гри на вулиці\nДоступна в різних розмірах для дітей різного віку."]
                elif player:
                    abouts = [f"👕 Дитяча футбольна форма у стилі {player}.\n\t• Дихаюча тканина\n\t• Принт “{player}”\n\t• Підходить для тренувань, ігор і повсякденного носіння\nРекомендована для дітей віком 5–16 років.",
                             f"⚽️ Комплект дитячої форми {player} — ідеальний вибір для активних дітей.\n\t• Високоякісний поліестер, приємний до тіла\n\t• Яскравий дизайн у стилі {player}\n\t• Футболка + шорти, еластичний пояс\nФорма не сковує рухів і легко переться.",
                             f"📦 У комплекті: футболка та шорти {player}\n\t• Стильна репліка з іменем та номером легендарного гравця\n\t• Виготовлена з легкого, дихаючого матеріалу\n\t• Добре підходить для футбольних секцій і гри на вулиці\nДоступна в різних розмірах для дітей різного віку."]
                else:
                    abouts = [(
                        "◻️Матеріал: поліестер – дихаючий та приємний до тіла\n"
                        "◻️Рукав: короткий\n"
                        "◻️Колір: див. фото"
                    )]
                about=""
                temp = abouts[0]
                if len(abouts) == 1:
                    about = abouts[0]
                else:
                    about = random.choice(abouts)
                    while about == temp:
                        about = random.choice(abouts)

        props = ""
        for prop in list(data['availabilityForProperties'].keys()):
            if prop.lower() != "null" and prop.strip():
                if data['availabilityForProperties'][prop] != 0:
                    props += f"⬛️ {prop.strip()}\n"
        if not props:
            log(user_id, f'{art} is unavailable')
            props = "Немає в наявності"
        else:
            log(user_id, f'{art} availability parsed')

        priceForProperties = data['priceForProperties']
        price_list = list(set(priceForProperties.values()))
        if len(price_list) == 1:
            price_str = f"{price_list[0]} грн"
        elif price_list:
            try:
                min_price = min([int(p) for p in price_list if str(p).isdigit()])
                price_str = f"від {min_price} грн"
            except:
                log(user_id, f'{art} contains non-digit prices')
                price_str = "Ціну уточнюйте"
        else:
            log(user_id, f'{art} has no prices for properties')
            price_str = "Ціну уточнюйте"

        hashtags = {"#форма"}
        name_lower = name.lower()
        for word, tag in [
            ("ronaldo", "#ronaldo"),
            ("messi", "#messi"),
            ("mbappe", "#mbappe"),
            ("mudryk", "#mudryk"),
            ("dovbyk", "#dovbyk"),
            ("nike", "#nike"),
            ("adidas", "#adidas"),
            ("puma", "#puma"),
            ("select", "#select"),
            ("umbro", "#umbro"),
        ]:
            if word in name_lower:
                hashtags.add(tag)
        hashtag_str = ' '.join(hashtags)
        log(user_id, f'Hashtags set for {art}: {hashtag_str}')

        szResultMessage = (
            f"🔥<b>{name}</b>🔥\n\n"
            f"Арт.: {art}\n\n"
            f"{about}\n\n"
            f"Доступні розміри:\n{props}\n"
            f"💲 Ціна: <b>{price_str}</b> 💲\n\n"
            f'Для замовлення пишіть - <a href="tg://user?id={bot.get_me().id}">Бот🤖</a>\n\n'
            f"{hashtag_str}"
        )
        log(user_id, f'Message formed successfully for {art}')
        return szResultMessage

    except Exception as e:
        log(user_id, f'[ERROR] Failed to form message for {data.get("art", "---")}: {e}')
        return "NULL"


def sendMessage():
    try:
        DataList = fetch_as_dicts("SELECT * FROM products")
        log_sys(f'{len(DataList)} products fetched from database')

        for idx, data in enumerate(DataList):
            if idx == config["LastSendedIndex"]:
                art = data.get("art", "---")
                if data.get('active', False):
                    log_sys(f'Processing active product: {art}')
                    items = fetch_as_dicts(f'SELECT * FROM product_properties WHERE art = ?', (art,))
                    data['availabilityForProperties'] = {}
                    data['priceForProperties'] = {}
                    for item in items:
                        data['availabilityForProperties'][item["property"]] = item['availability']
                        data['priceForProperties'][item["property"]] = item['price']
                    log_sys(f'Properties loaded for {art}')

                    szResultMessage = formMessageText(data, 'system')
                    images = []

                    try:
                        if data.get("frontImage"):
                            images.append(open(data["frontImage"], 'rb'))
                            log_sys(f'Front image added for {art}')
                        if data.get("backImage"):
                            images.append(open(data["backImage"], 'rb'))
                            log_sys(f'Back image added for {art}')
                    except Exception as e:
                        log_sys(f'[ERROR] Failed to open image for {art}: {e}')

                    if images:
                        media = []
                        for i, img in enumerate(images):
                            if i == 0:
                                media.append(types.InputMediaPhoto(img, caption=szResultMessage, parse_mode='HTML'))
                            else:
                                media.append(types.InputMediaPhoto(img))
                        bot.send_media_group(config["channelID"], media)
                        log_sys(f'Message with images sent for {art}')
                    else:
                        bot.send_message(config["channelID"], szResultMessage, parse_mode='HTML')
                        log_sys(f'Message without images sent for {art}')

                    config["LastSendedIndex"] += 1
                    log_sys(f'LastSendedIndex updated to {config["LastSendedIndex"]}')

                    with open("config.json", "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=4, ensure_ascii=False)
                        log_sys(f'Config saved after sending {art}')
                    return
                else:
                    log_sys(f'{art} is inactive, skipping')
                    config["LastSendedIndex"] += 1
                    with open("config.json", "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=4, ensure_ascii=False)
                    sendMessage()

        log_sys(f'All products processed. Restarting index')
        config["LastSendedIndex"] = 0
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        log_sys(f'LastSendedIndex reset to 0')
        sendMessage()

    except Exception as e:
        log_sys(f'[ERROR] Failed to send message: {e}')

for hour in range(config["fromHour"], config["toHour"]):
    time_str = f"{hour:02d}:00"
    schedule.every().day.at(time_str).do(sendMessage)

def run_scheduler():
    global scheduler_running
    while True:
        if scheduler_running:
            schedule.run_pending()
        time.sleep(config['timeToSleep'])

scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.start()

try:
    bot.infinity_polling()
except Exception as e:
    log_sys(f"[ERROR] Bot polling failed: {e}")
    input("Press Enter to exit...")