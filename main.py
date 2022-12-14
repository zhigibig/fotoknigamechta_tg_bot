import pyrogram
import asyncio
import threading
import random
from datetime import datetime
from pyrogram import Client, idle, filters, types, errors
from pyrogram.types import Message, Update
from pyrogram.raw.functions.messages import SendMedia, SetBotPrecheckoutResults
from pyrogram.raw.types import (
    DataJSON,
    InputMediaInvoice,
    Invoice,
    LabeledPrice,
    MessageActionPaymentSentMe,
    UpdateBotPrecheckoutQuery,
    UpdateNewMessage,
)
from secrets import API_ID, API_HASH, BOT_TOKEN, ADMIN_TOKEN, PAYMENT_TOKEN
import os
from peewee import *

# Telegram shopping bot with ordering system
# Written with Pyrogram library

db = SqliteDatabase("data.db")

PRIVATE_EX_ID = -1001605432449


class User(Model):
    id = IntegerField(primary_key=True)
    email = CharField(max_length=255, null=True)
    phone = CharField(max_length=255, null=True)
    name = CharField(max_length=255, null=True)

    class Meta:
        database = db


class Product(Model):
    title = CharField(max_length=255, null=True, primary_key=True)
    id = IntegerField(null=True)
    examples = CharField(max_length=255, null=True)
    materials_type = TextField(null=True)
    image = CharField(max_length=255, null=True)
    caption = TextField(null=True)
    needed_info = TextField(null=True)
    is_active = BooleanField(default=True)

    class Meta:
        database = db


class Order(Model):
    id = IntegerField(primary_key=True)
    user = ForeignKeyField(User, backref='orders')
    product = ForeignKeyField(Product, backref='orders')
    needed_info = TextField(null=True)
    materials = CharField(max_length=255, null=True)
    date = DateTimeField(default=datetime.now)
    price = FloatField(null=True)
    is_paid = BooleanField(default=False)
    state = CharField(max_length=255, null=True)

    class Meta:
        database = db


db.create_tables([User, Product, Order])

bot_app = Client("bot", API_ID, API_HASH, bot_token=BOT_TOKEN)
bot_p_app = Client("bot_p", API_ID, API_HASH, bot_token=BOT_TOKEN)
admin_app = Client("admin", API_ID, API_HASH, bot_token=ADMIN_TOKEN)

admins = [316490607, 545585117]
conv_dict = {}  # {user_id: [query, message]}


def get_user(user_id):
    user = User.get_or_none(User.id == user_id)
    if user is None:
        user = User(id=user_id)
        user.save(force_insert=True)
    return user


MENU_BUTTONS = [
    [types.InlineKeyboardButton("Продукты", callback_data="products")],
    [types.InlineKeyboardButton("Активные заказы", callback_data="orders")],
    [types.InlineKeyboardButton("Все заказы", callback_data="all_order")],
    # [types.InlineKeyboardButton("Настройки", callback_data="settings")]
]
MENU_TEXT = "Привет, {}! Выбери действие:"


def send_menu(user_id):
    user = get_user(user_id)
    keyboard = types.InlineKeyboardMarkup(MENU_BUTTONS)

    bot_app.send_message(
        user_id,
        MENU_TEXT.format(user.name),
        reply_markup=keyboard
    )


def edit_menu(user_id, message_id):
    user = get_user(user_id)

    keyboard = types.InlineKeyboardMarkup(MENU_BUTTONS)

    bot_app.edit_message_text(
        user_id,
        message_id,
        MENU_TEXT.format(user.name),
        reply_markup=keyboard
    )


def send_info_to_admins(text):
    for admin in admins:
        try:
            admin_app.send_message(admin, text)
        except:
            pass


def create_payment(user_id, order_id, price, title="Test payment", description="Description"):
    user = get_user(user_id)
    order = Order.get_or_none(Order.id == order_id)

    peer = bot_p_app.resolve_peer(user_id)

    bot_p_app.invoke(
        SendMedia(
            peer=peer,
            media=InputMediaInvoice(
                title=title,
                description=description,
                invoice=Invoice(
                    currency="RUB",
                    # prices needs to be a list, even for a single item
                    prices=[LabeledPrice(label=title, amount=int(price) * 100)],
                    test=True,
                ),
                payload=bytes(str(order_id), "utf-8"),
                provider=PAYMENT_TOKEN,
                provider_data=DataJSON(data=r"{}"),
                start_param="pay",
            ),
            message="",
            random_id=bot_p_app.rnd_id(),
        )
    )


def get_photo_from_ex(client, message_id):
    return client.get_messages(chat_id=PRIVATE_EX_ID, message_ids=int(message_id)).photo.file_id


def get_document_from_ex(client, message_id):
    return client.get_messages(chat_id=PRIVATE_EX_ID, message_ids=int(message_id)).document.file_id


def send_media_group_from_ex(client, chat_id, message_id):
    return client.copy_media_group(from_chat_id=PRIVATE_EX_ID, chat_id=chat_id, message_id=int(message_id))[0].id


def send_media_group_to_ex(client, chat_id, message_id):
    return client.copy_media_group(from_chat_id=chat_id, chat_id=PRIVATE_EX_ID, message_id=int(message_id))[0].id


def send_media_to_ex(client, file_id):
    cache_mess = client.send_cached_media(chat_id=PRIVATE_EX_ID, file_id=file_id)
    return cache_mess.id


@bot_app.on_message(filters.command("start"))
def on_start_command(client, message):
    user_id = message.from_user.id
    user = get_user(user_id)

    # Ask user for email, phone, name using inline keyboard

    if user.phone:
        send_menu(user_id)
    else:
        buttons = [
            [types.InlineKeyboardButton(
                text="Ввести данные",
                callback_data="email"
            )]
        ]

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        message.reply_text(
            "Привет! Я бот Фотокнига Мечта.\n"
            "Пожалуйста, введите ваши контактные данные в следующем окне.",
            reply_markup=keyboard
        )

        # Save user data
        user.email = None
        user.phone = None
        user.name = None
        user.save()


# Handle email input
@bot_app.on_callback_query(filters.regex("email"))
def on_email_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    # Ask user for email
    message = callback_query.message
    message_repl = bot_app.send_message(
        user_id,
        "Пожалуйста, введите email.",
        reply_markup=types.ForceReply(selective=True, placeholder="john@mail.ru")
    )
    conv_dict[user_id] = ['email', message_repl]
    # Save user data

    bot_app.answer_callback_query(callback_query.id, text="Введите email")


# Handle the reply to email input
@bot_app.on_message(filters.reply)
def on_data_reply(client, message):
    user_id = message.from_user.id
    user = get_user(user_id)

    if conv_dict.get(user_id)[1].id == message.reply_to_message.id and conv_dict.get(user_id)[0] == 'email':
        # Save user data
        user.email = message.text
        user.save()

        # Ask user for phone
        conv_mess = message.reply_text(
            "Пожалуйста, введите ваш номер телефона.",
            reply_markup=types.ForceReply(selective=True, placeholder="+7XXXXXXXXXX")
        )
        conv_dict[user_id] = ['phone', conv_mess]

        # Save user data

    if conv_dict.get(user_id)[1].id == message.reply_to_message.id and conv_dict.get(user_id)[0] == 'phone':
        # Save user data
        user.phone = message.text
        user.save()

        # Ask user for name
        conv_mess = message.reply_text(
            "Пожалуйста, введите ваше имя.",
            reply_markup=types.ForceReply(selective=True, placeholder="Джон Эплсид")
        )
        conv_dict[user_id] = ['name', conv_mess]

    if conv_dict.get(user_id)[1].id == message.reply_to_message.id and conv_dict.get(user_id)[0] == 'name':
        # Save user data
        user.name = message.text
        user.save()
        conv_dict.pop(user_id)

        bot_app.send_message(
            user_id,
            "Ваши данные успешно записаны.",
        )

        send_menu(user_id)

    if conv_dict.get(user_id)[1].id == message.reply_to_message.id and conv_dict.get(user_id)[0] == 'get_order_info':
        user_id = message.from_user.id
        user = get_user(user_id)

        order_id = int(message.reply_to_message.text.split('|')[0])
        order = Order.get_or_none(Order.id == order_id)

        order.needed_info = message.text
        order.save()

        text = "{}| Прикрепите необходимые файлы **одним архивом**.\n\n__{}__"
        conv_mess = bot_app.send_message(
            text=text.format(str(order.id), order.product.materials_type),
            chat_id=user_id,
            reply_markup=types.ForceReply(selective=True, placeholder="Прикрепите файлы")
        )
        conv_dict[user_id] = ['get_order_materials', conv_mess]

    if conv_dict.get(user_id)[1].id == message.reply_to_message.id and \
            conv_dict.get(user_id)[0] == 'get_order_materials':
        user_id = message.from_user.id
        user = get_user(user_id)

        order_id = int(message.reply_to_message.text.split('|')[0])
        order = Order.get_or_none(Order.id == order_id)

        order.materials = send_media_to_ex(bot_app, message.document.file_id)

        order.state = "Создан"
        order.save()

        conv_dict.pop(user_id)

        bot_app.send_message(
            user_id,
            "Ваш заказ успешно отправлен в обработку.",
        )
        send_info_to_admins("Новый заказ №{} от {}".format(str(order.id), user.name))

        send_menu(user_id)


# on back button
@bot_app.on_callback_query(filters.regex("back"))
def on_back_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    edit_menu(user_id, callback_query.message.id)
    bot_app.answer_callback_query(callback_query.id, text="Принято")


# on products menu
@bot_app.on_callback_query(filters.regex("products"))
def on_products_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    text = "Выберите продукт:"
    buttons = []
    for product in Product.select():
        if product.is_active:
            buttons.append([types.InlineKeyboardButton(
                text=product.title,
                callback_data="product_{}".format(str(product.id))
            )])

    if not buttons:
        text = "Нет доступных продуктов."

    buttons.append([types.InlineKeyboardButton(
        text="↩️",
        callback_data="back"
    )])
    keyboard = types.InlineKeyboardMarkup(buttons)

    bot_app.edit_message_text(
        user_id,
        callback_query.message.id,
        text,
        reply_markup=keyboard
    )

    bot_app.answer_callback_query(callback_query.id, text="Принято")


# on orders menu
@bot_app.on_callback_query(filters.regex("orders"))
def on_orders_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    text = "Выберите заказ:"
    buttons = []
    for order in Order.select():
        if not (order.state in ['Создается', 'Отменен', 'Выполнен']):
            buttons.append([types.InlineKeyboardButton(
                text=order.product.title + " | " + order.state,
                callback_data="order_{}".format(order.id)
            )])
    if not buttons:
        text = "Нет доступных заказов."
    buttons.append([types.InlineKeyboardButton(
        text="↩️",
        callback_data="back"
    )])

    keyboard = types.InlineKeyboardMarkup(buttons)

    bot_app.edit_message_text(
        text=text,
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.id,
        reply_markup=keyboard
    )
    bot_app.answer_callback_query(callback_query.id, text="Принято")


# on orders menu
@bot_app.on_callback_query(filters.regex("all_order"))
def on_all_orders_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    text = "Выберите заказ:"
    buttons = []
    for order in Order.select():
        if not (order.state in ['Создается']):
            buttons.append([types.InlineKeyboardButton(
                text=order.product.title + " | " + order.state,
                callback_data="order_{}".format(order.id)
            )])
    if not buttons:
        text = "Нет доступных заказов."
    buttons.append([types.InlineKeyboardButton(
        text="↩️",
        callback_data="back"
    )])

    keyboard = types.InlineKeyboardMarkup(buttons)

    bot_app.edit_message_text(
        text=text,
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.id,
        reply_markup=keyboard
    )
    bot_app.answer_callback_query(callback_query.id, text="Принято")


# # on settings menu
# @bot_app.on_callback_query(filters.regex("settings"))
# def on_settings_callback(client, callback_query):
#     user_id = callback_query.from_user.id
#     user = get_user(user_id)
#
#     text = "Выберите настройку:"
#     buttons = [[types.InlineKeyboardButton(
#         text="Изменить номер телефона",
#         callback_data="change_phone"
#     )], [types.InlineKeyboardButton(
#         text="Изменить email",
#         callback_data="change_email"
#     )],
#         [types.InlineKeyboardButton(
#             text="↩️",
#             callback_data="back"
#         )]
#     ]

    keyboard = types.InlineKeyboardMarkup(buttons)

    bot_app.edit_message_text(
        text=text,
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.id,
        reply_markup=keyboard
    )

    bot_app.answer_callback_query(callback_query.id, text="Принято")


# on order callback
@bot_app.on_callback_query(filters.regex("order_(\d+)"))
def on_view_order_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    order_id = int(callback_query.data.split('_')[-1])
    order = Order.get_or_none(Order.id == order_id)

    if order is None:
        bot_app.answer_callback_query(callback_query.id, text="Заказ не найден.", show_alert=True)
        return

    buttons = []
    text = "Error"
    if order.state == "Создан":
        text = "Заказ №{}:\n\nСтатус: {}\n\nДоп. Информация: {}\n\n".format(order.id, order.state, order.needed_info)
        text += "Цена еще не определена."
        buttons.append([types.InlineKeyboardButton(
            text="Отменить заказ",
            callback_data="cancel_ord_{}".format(order.id)
        )])
    elif order.state == "Не оплачен":
        text = "Заказ №{}:\n\nСтатус: {}\n\nДоп. Информация: {}\n\n".format(order.id, order.state, order.needed_info)
        text += "Цена: {} р".format(order.price)
        buttons.append([types.InlineKeyboardButton(
            text="Отменить заказ",
            callback_data="cancel_ord_{}".format(order.id)
        )])
        buttons.append([types.InlineKeyboardButton(
            text="Оплатить",
            callback_data="pay_frd_{}".format(order.id)
        )])
    elif order.state in ["В процессе", "Выполнен", "Отменен"]:
        text = "Заказ №{}:\n\nСтатус: {}\n\nДоп. Информация: {}\n\n".format(order.id, order.state, order.needed_info)
        text += "Цена: {} р".format(order.price)
        buttons.append([types.InlineKeyboardButton(
            text="Обсудить заказ",
            url="t.me/tblackcat"
        )])
    buttons.append([types.InlineKeyboardButton(
        text="↩️",
        callback_data="delete_message"
    )])

    bot_app.send_message(
        text=text,
        chat_id=callback_query.message.chat.id,
        reply_markup=types.InlineKeyboardMarkup(buttons)
    )

    bot_app.answer_callback_query(callback_query.id, text="Принято")


# on cancel order callback
@bot_app.on_callback_query(filters.regex("cancel_ord_(\d+)"))
def on_cancel_order_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    order_id = int(callback_query.data.split('_')[-1])
    order = Order.get_or_none(Order.id == order_id)

    if order.state in ["Создан", "Не оплачен"]:
        order.state = "Отменен"
        order.save()
        bot_app.delete_messages(user_id, callback_query.message.id)
        send_info_to_admins("Заказ №{} отменен клиентом.".format(order.id))
        bot_app.answer_callback_query(callback_query.id, text="Заказ отменен", show_alert=True)
    else:
        bot_app.answer_callback_query(callback_query.id, text="Заказ не может быть отменен", show_alert=True)


# on delete_message callback
@bot_app.on_callback_query(filters.regex("delete_message"))
def on_delete_message_callback(client, callback_query):
    bot_app.delete_messages(
        chat_id=callback_query.message.chat.id,
        message_ids=callback_query.message.id
    )

    bot_app.answer_callback_query(callback_query.id, text="Принято")


# on pay order callback
@bot_app.on_callback_query(filters.regex("pay_frd_(\d+)"))
def on_pay_order_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    order_id = int(callback_query.data.split('_')[-1])
    order = Order.get_or_none(Order.id == order_id)
    if order.state != "Не оплачен":
        bot_app.answer_callback_query(callback_query.id, text="Этот заказ невозможно оплатить", show_alert=True)
    else:
        create_payment(user_id, order_id, order.price, order.product.title, order.product.caption)
        bot_app.answer_callback_query(callback_query.id, text="Принято")


# on product callback
@bot_app.on_callback_query(filters.regex("product_(\d+)"))
def on_product_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    product_id = int(callback_query.data.split('_')[-1])
    product = Product.get(Product.id == product_id)

    text = "{}\n\nОписание:\n{}"
    buttons = [
        [types.InlineKeyboardButton(
            text="Заказать",
            callback_data="buy_{}".format(str(product.id))
        )],
        [types.InlineKeyboardButton(
            text="Примеры",
            callback_data="show_examples_{}".format(str(product.id))
        )],
        [types.InlineKeyboardButton(
            text="↩️",
            callback_data="delete_message"
        )]]

    keyboard = types.InlineKeyboardMarkup(buttons)
    if product.image:
        file_id = get_photo_from_ex(bot_app, product.image)
        bot_app.send_cached_media(
            caption=text.format(product.title, product.caption),
            chat_id=callback_query.message.chat.id,
            reply_markup=keyboard,
            file_id=file_id
        )
    else:
        bot_app.send_message(
            text=text.format(product.title, product.caption),
            chat_id=callback_query.message.chat.id,
            reply_markup=keyboard
        )

    bot_app.answer_callback_query(callback_query.id, text="Принято")


# on show_examples callback
@bot_app.on_callback_query(filters.regex("show_examples_(\d+)"))
def on_show_examples_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    product_id = int(callback_query.data.split('_')[-1])
    product = Product.get(Product.id == product_id)

    send_media_group_from_ex(bot_app, user_id, product.examples)
    on_product_callback(client, callback_query)
    bot_app.delete_messages(user_id, callback_query.message.id)

    bot_app.answer_callback_query(callback_query.id, text="Примеры")


# on buy callback
@bot_app.on_callback_query(filters.regex("buy_(\d+)"))
def on_buy_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    product_id = int(callback_query.data.split('_')[-1])
    product = Product.get(Product.id == product_id)

    if product.is_active:
        order = Order.create(
            id=_generate_id(),
            user=user,
            product=product,
            state="Создается"
        )
        order.save()

        text = "{}| Введите следующую информацию:\n__{}__"

        conv_mess = bot_app.send_message(
            text=text.format(str(order.id), product.needed_info),
            chat_id=user_id,
            reply_markup=types.ForceReply(selective=True, placeholder="Введите информацию")
        )

        conv_dict[user_id] = ["get_order_info", conv_mess]
        bot_app.answer_callback_query(callback_query.id, text="Принято")
    else:
        bot_app.answer_callback_query(callback_query.id, text="Этот продукт недоступен.", show_alert=True)


@bot_p_app.on_raw_update()
def raw_update(app: Client, update: Update, users: dict, chats: dict):
    if isinstance(update, UpdateBotPrecheckoutQuery):
        # This is to tell Telegram that everything is okay with this order.
        app.invoke(SetBotPrecheckoutResults(query_id=update.query_id, success=True))

    if (
            isinstance(update, UpdateNewMessage)
            and hasattr(update.message, "action")
            and isinstance(update.message.action, MessageActionPaymentSentMe)
    ):
        user_id = update.message.peer_id.user_id
        order_id = update.message.action.payload
        order = Order.get_or_none(Order.id == order_id)
        order.state = "В процессе"
        order.save()
        # Sending a message confirming the order (additional to TGs service message)
        bot_app.send_message(user_id, 'Заказ №{} оплачен.'.format(order_id))
        send_info_to_admins("Заказ №{} оплачен.".format(order_id))
        send_menu(user_id)


# ADMIN SECTION


adm_conv_dict = {}  # {user_id: [conv_type, conv_mess]}

ADMIN_MENU_TEXT = "Выберите действие:"
ADMIN_MENU_BUTTONS = [[types.InlineKeyboardButton(
    text="Активные заказы",
    callback_data="admin_orders"
)], [types.InlineKeyboardButton(
    text="Все заказы",
    callback_data="admin_all_order"
)], [types.InlineKeyboardButton(
    text="Управление продуктами",
    callback_data="admin_products"
)]]


def send_admin_menu(user_id):
    keyboard = types.InlineKeyboardMarkup(ADMIN_MENU_BUTTONS)

    admin_app.send_message(
        user_id,
        ADMIN_MENU_TEXT,
        reply_markup=keyboard
    )


def edit_admin_menu(user_id, message_id):
    keyboard = types.InlineKeyboardMarkup(ADMIN_MENU_BUTTONS)

    admin_app.edit_message_text(
        message_id=message_id,
        chat_id=user_id,
        text=ADMIN_MENU_TEXT,
        reply_markup=keyboard
    )


def _generate_id():
    return random.randint(1, 2000000000)


def admin_get_product(product_title):
    product = Product.get_or_none(Product.title == product_title)
    if product is None:
        product = Product.create(id=_generate_id(), title=product_title, is_active=True)
        product.save()
    return product


@admin_app.on_message(filters.command("start"))
def on_admin_start_command(client, message):
    user_id = message.from_user.id

    if user_id in admins:
        send_admin_menu(user_id)


# on admin product control menu
@admin_app.on_callback_query(filters.regex("admin_products"))
def on_admin_products_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    text = "Выберите действие:"
    buttons = [[types.InlineKeyboardButton(
        text="Добавить продукт",
        callback_data="admin_add_product"
    )], [types.InlineKeyboardButton(
        text="Список продуктов",
        callback_data="admin_list_products"
    )],
        [types.InlineKeyboardButton(
            text="↩️",
            callback_data="back"
        )]]

    keyboard = types.InlineKeyboardMarkup(buttons)

    admin_app.edit_message_text(
        user_id,
        callback_query.message.id,
        text,
        reply_markup=keyboard
    )

    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin product add menu
@admin_app.on_callback_query(filters.regex("admin_add_product"))
def on_admin_add_product_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user = get_user(user_id)

    text = "Введите название продукта или '-' если хотите отменить"

    # using ForceReply
    admin_app.edit_message_text(
        user_id,
        callback_query.message.id,
        "Создание нового продукта"
    )

    conv_message = admin_app.send_message(
        user_id,
        text,
        reply_markup=types.ForceReply(selective=True, placeholder="Продукт")
    )

    adm_conv_dict[user_id] = ['product_name', conv_message]
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on get product name admin
@admin_app.on_message(filters.reply)
def on_admin_get_product_name(client, message):
    user_id = message.from_user.id

    if adm_conv_dict[user_id][0] == 'product_name' and adm_conv_dict[user_id][1].id == message.reply_to_message.id:
        if message.text == '-':
            return admin_app.delete_messages(user_id, [message.reply_to_message.id, message.id])
        product_name = message.text
        product = admin_get_product(product_name)

        # Add caption for product
        text = "{}| Введите описание продукта"
        conv_mess = admin_app.send_message(
            user_id,
            text.format(product_name),
            reply_markup=types.ForceReply(selective=True, placeholder="Описание")
        )

        adm_conv_dict[user_id] = ['product_desc', conv_mess]

    if adm_conv_dict[user_id][0] == 'product_desc' and adm_conv_dict[user_id][1].id == message.reply_to_message.id:
        product_desc = message.text
        product_name = message.reply_to_message.text.split("|")[0]
        product = admin_get_product(product_name)
        product.caption = product_desc
        product.save()

        text = "{}| Прикрепите изображение или введите -"
        conv_mess = admin_app.send_message(
            user_id,
            text.format(product_name),
            reply_markup=types.ForceReply(selective=True, placeholder="Прикрепите изображение")
        )

        adm_conv_dict[user_id] = ['product_pic', conv_mess]

    if adm_conv_dict[user_id][0] == 'product_pic' and adm_conv_dict[user_id][1].id == message.reply_to_message.id:
        product_name = message.reply_to_message.text.split("|")[0]
        product = admin_get_product(product_name)
        if message.text == "-":
            product.image = None
        else:
            product.image = send_media_to_ex(admin_app, message.photo.file_id)
        product.save()
        text = "{}| Прикрепите примеры продукта одним альбомом (видео и/или фото) или введите -"
        conv_mess = admin_app.send_message(
            user_id,
            text.format(product_name),
            reply_markup=types.ForceReply(selective=True, placeholder="Фото и/или видео")
        )

        adm_conv_dict[user_id] = ['product_examples', conv_mess]

    if adm_conv_dict[user_id][0] == 'product_examples' and adm_conv_dict[user_id][1].id == message.reply_to_message.id:
        adm_conv_dict[user_id] = ['product_info', None]

        product_name = message.reply_to_message.text.split("|")[0]
        product = admin_get_product(product_name)
        if message.text == "-":
            product.examples = None
        else:
            product.examples = send_media_group_to_ex(admin_app, user_id, message.id)
        product.save()

        text = "{}| Введите необходимую информацию от клиента (например: количество, подробности)"
        conv_mess = admin_app.send_message(
            user_id,
            text.format(product_name),
            reply_markup=types.ForceReply(selective=True, placeholder="Информация")
        )

        adm_conv_dict[user_id] = ['product_info', conv_mess]

    if adm_conv_dict[user_id][0] == 'product_info' and adm_conv_dict[user_id][1].id == message.reply_to_message.id:
        product_info = message.text
        product_name = message.reply_to_message.text.split("|")[0]
        product = admin_get_product(product_name)
        product.needed_info = product_info
        product.save()

        text = "{}| Введите тип материалов, которые необходимо прикрепить клиенту (например .psd файл)"
        conv_mess = admin_app.send_message(
            user_id,
            text.format(product_name),
            reply_markup=types.ForceReply(selective=True, placeholder="Тип материалов")
        )

        adm_conv_dict[user_id] = ['product_materials', conv_mess]

    if adm_conv_dict[user_id][0] == 'product_materials' and adm_conv_dict[user_id][1].id == message.reply_to_message.id:
        product_materials = message.text
        product_name = message.reply_to_message.text.split("|")[0]
        product = admin_get_product(product_name)
        product.materials_type = product_materials
        product.save()

        text = "{}| Продукт успешно создан. Чтобы управлять им, найдите его в списке продуктов."
        admin_app.send_message(
            user_id,
            text.format(product_name)
        )
        adm_conv_dict.pop(user_id)

        send_admin_menu(user_id)

    if adm_conv_dict.get(user_id)[0] == 'admin_set_price' and \
            adm_conv_dict.get(user_id)[1].id == message.reply_to_message.id:
        user_id = message.from_user.id
        order_id = int(message.reply_to_message.text.split("|")[0])
        order = Order.get(id=order_id)

        price = float(message.text)
        order.price = price
        order.state = "Не оплачен"
        order.save()

        admin_app.delete_messages(user_id, [message.id, message.reply_to_message.id])
        admin_app.send_message(user_id, "Цена заказа успешно изменена.")
        bot_app.send_message(order.user.id, "Заказ №{} принят и ожидает оплаты.".format(order.id))


# on admin product list menu
@admin_app.on_callback_query(filters.regex("admin_list_products"))
def on_admin_list_products_callback(client, callback_query):
    user_id = callback_query.from_user.id

    text = "Выберите продукт для редактирования:"
    buttons = []
    for product in Product.select():
        buttons.append([types.InlineKeyboardButton(
            text=product.title,
            callback_data="admin_edit_product_{}".format(str(product.id))
        )])

    buttons.append([types.InlineKeyboardButton(
        text="↩️",
        callback_data="back"
    )])

    keyboard = types.InlineKeyboardMarkup(buttons)

    admin_app.edit_message_text(
        user_id,
        callback_query.message.id,
        text,
        reply_markup=keyboard
    )
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin product edit menu
@admin_app.on_callback_query(filters.regex("admin_edit_product_(\d+)"))
def on_admin_edit_product_callback(client, callback_query):
    user_id = callback_query.from_user.id

    product_id = int(callback_query.data.split("_")[-1])
    product = Product.get_or_none(Product.id == product_id)

    text = "{}\n\nОписание:\n{}\nНеобходимая информация:\n{}\nВыберите действие:"
    # buttons: freeze, delete, edit caption, edit info, back
    buttons = [
        [types.InlineKeyboardButton(
            text=("Заморозить" if product.is_active else "Разморозить"),
            callback_data="admin_freeze_product_{}".format(str(product.id))
        )],
        [types.InlineKeyboardButton(
            text="Удалить",
            callback_data="admin_delete_product_{}".format(str(product.id))
        )],
        [types.InlineKeyboardButton(
            text="↩️",
            callback_data="admin_delete_message"
        )]
    ]

    keyboard = types.InlineKeyboardMarkup(buttons)

    admin_app.send_message(
        user_id,
        text.format(product.title, product.caption, product.needed_info),
        reply_markup=keyboard
    )
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin product freeze menu
@admin_app.on_callback_query(filters.regex("admin_freeze_product_(\d+)"))
def on_admin_freeze_product_callback(client, callback_query):
    user_id = callback_query.from_user.id

    product_id = int(callback_query.data.split("_")[-1])
    product = Product.get_or_none(Product.id == product_id)

    product.is_active = not product.is_active
    product.save()

    text = "{} разморожен." if product.is_active else "{} заморожен."

    admin_app.edit_message_text(
        user_id,
        callback_query.message.id,
        text.format(product.title)
    )

    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin product delete menu
@admin_app.on_callback_query(filters.regex("admin_delete_product_(\d+)"))
def on_admin_delete_product_callback(client, callback_query):
    user_id = callback_query.from_user.id

    product_id = int(callback_query.data.split("_")[-1])
    product = Product.get_or_none(Product.id == product_id)

    text = None
    if product.orders.count() > 0:
        text = "Продукт не может быть удален, так как он привязан к заказам. " \
               "Удалите все заказы привязанные к продукту и попробуйте снова."
    else:
        product.delete_instance()
        text = "{} удален.".format(product.title)

    admin_app.edit_message_text(
        user_id,
        callback_query.message.id,
        text
    )

    send_admin_menu(user_id)
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin active orders menu
@admin_app.on_callback_query(filters.regex("admin_orders"))
def on_admin_orders_callback(client, callback_query):
    user_id = callback_query.from_user.id

    text = "Выберите заказ для редактирования:"
    buttons = []
    for order in Order.select():
        if not (order.state in ["Создается", "Отменен", "Выполнен"]):
            buttons.append([types.InlineKeyboardButton(
                text=str(order.id) + " | " + order.state,
                callback_data="admin_edit_order_{}".format(str(order.id))
            )])

    buttons.append([types.InlineKeyboardButton(
        text="↩️",
        callback_data="back"
    )])

    keyboard = types.InlineKeyboardMarkup(buttons)

    admin_app.edit_message_text(
        user_id,
        callback_query.message.id,
        text,
        reply_markup=keyboard
    )
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin all orders menu
@admin_app.on_callback_query(filters.regex("admin_all_order"))
def on_admin_orders_callback(client, callback_query):
    user_id = callback_query.from_user.id

    text = "Выберите заказ для редактирования:"
    buttons = []
    for order in Order.select():
        if not (order.state in ["Создается"]):
            buttons.append([types.InlineKeyboardButton(
                text=str(order.id) + " | " + order.state,
                callback_data="admin_edit_order_{}".format(str(order.id))
            )])

    buttons.append([types.InlineKeyboardButton(
        text="↩️",
        callback_data="back"
    )])

    keyboard = types.InlineKeyboardMarkup(buttons)

    admin_app.edit_message_text(
        user_id,
        callback_query.message.id,
        text,
        reply_markup=keyboard
    )
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin edit order
@admin_app.on_callback_query(filters.regex("admin_edit_order_(\d+)"))
def on_admin_edit_order_callback(client, callback_query):
    user_id = callback_query.from_user.id

    order_id = int(callback_query.data.split("_")[-1])
    order = Order.get_or_none(Order.id == order_id)
    if order is None:
        admin_app.answer_callback_query(callback_query.id, text="Заказ не найден", show_alert=True)
        return

    buttons = []
    text = ""
    if order.state == "Создан":
        buttons.append([types.InlineKeyboardButton(
            "Задать цену", callback_data="admin_set_price_{}".format(str(order.id)))])
        buttons.append([types.InlineKeyboardButton(
            "Отменить", callback_data="admin_cancel_ord_{}".format(str(order.id)))])

        text = "Заказ №{}\n**Статус:** {}\n\n**Дата:** {}\n\n**Информация:\n**__{}__\n\n" \
               "**Контактная информация:**\n" \
               "e-mail: {}\n" \
               "телефон: {}\n\n" \
               "Выберите действие:".format(str(order.id), order.state, order.date.strftime("%d.%m.%Y, %H:%M"),
                                           order.needed_info, order.user.email, order.user.phone)
    elif order.state == "Не оплачен":
        buttons.append([types.InlineKeyboardButton(
            "Отменить", callback_data="admin_cancel_ord_{}".format(str(order.id)))])

        text = "Заказ №{}\n**Статус:** {}\n\n**Цена:** {} р\n\n**Дата:** {}\n\n**Информация:\n**__{}__\n\n" \
               "**Контактная информация:**\n" \
               "e-mail: {}\n" \
               "телефон: {}\n\n" \
               "Выберите действие:".format(str(order.id), order.state, order.price,
                                           order.date.strftime("%d.%m.%Y, %H:%M"),
                                           order.needed_info, order.user.email, order.user.phone)
    elif order.state == "В процессе":
        buttons.append([types.InlineKeyboardButton(
            "Отменить", callback_data="admin_cancel_ord_{}".format(str(order.id)))])
        buttons.append([types.InlineKeyboardButton(
            "Завершить", callback_data="admin_complete_ord_{}".format(str(order.id)))])

        text = "Заказ №{}\n**Статус:** {}\n\n**Цена:** {} р\n\n**Дата:** {}\n\n**Информация:\n**__{}__\n\n" \
               "**Контактная информация:**\n" \
               "e-mail: {}\n" \
               "телефон: {}\n\n" \
               "Выберите действие:".format(str(order.id), order.state, order.price,
                                           order.date.strftime("%d.%m.%Y, %H:%M"),
                                           order.needed_info, order.user.email, order.user.phone)
    else:
        buttons.append([types.InlineKeyboardButton(
            "Удалить", callback_data="admin_delete_ord_{}".format(str(order.id)))])

        text = "Заказ №{}\n**Статус:** {}\n\n**Цена:** {} р\n\n**Дата:** {}\n\n**Информация:\n**__{}__\n\n" \
               "**Контактная информация:**\n" \
               "e-mail: {}\n" \
               "телефон: {}\n\n" \
               "Выберите действие:".format(str(order.id), order.state, order.price,
                                           order.date.strftime("%d.%m.%Y, %H:%M"),
                                           order.needed_info, order.user.email, order.user.phone)

    buttons.append([
        types.InlineKeyboardButton(
            "↩️",
            callback_data="admin_delete_message"
        )])
    keyboard = types.InlineKeyboardMarkup(buttons)

    admin_app.send_cached_media(
        chat_id=user_id,
        caption=text,
        file_id=get_document_from_ex(admin_app, order.materials),
        reply_markup=keyboard
    )
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# admin complete order callback
@admin_app.on_callback_query(filters.regex("admin_complete_ord_(\d+)"))
def on_admin_cancel_order_callback(client, callback_query):
    user_id = callback_query.from_user.id

    order_id = int(callback_query.data.split("_")[-1])
    order = Order.get_or_none(Order.id == order_id)

    if order.state in ["Отменен", "Выполнен"]:
        admin_app.answer_callback_query(callback_query.id,
                                        text="Невозможно отметить заказ как выполненный", show_alert=True)
    else:
        order.state = "Выполнен"
        order.save()
        bot_app.send_message(order.user.id, "Заказ №{} выполнен. Результат отправлен на почту.".format(str(order.id)))
        admin_app.delete_messages(user_id, callback_query.message.id)

        admin_app.answer_callback_query(callback_query.id, text="Заказ выполнен")


# admin cancel order callback
@admin_app.on_callback_query(filters.regex("admin_cancel_ord_(\d+)"))
def on_admin_cancel_order_callback(client, callback_query):
    user_id = callback_query.from_user.id

    order_id = int(callback_query.data.split("_")[-1])
    order = Order.get_or_none(Order.id == order_id)

    if order.state in ["Отменен", "Выполнен"]:
        admin_app.answer_callback_query(callback_query.id, text="Невозможно отменить заказ", show_alert=True)
    else:
        order.state = "Отменен"
        order.save()
        bot_app.send_message(order.user.id, "Заказ №{} отменен.\n"
                                            "За подробностями нажмите кнопку "
                                            "'Связаться' в заказе.".format(str(order.id)))

        admin_app.delete_messages(user_id, callback_query.message.id)

        admin_app.answer_callback_query(callback_query.id, text="Заказ отменен")


# admin cancel order callback
@admin_app.on_callback_query(filters.regex("admin_delete_ord_(\d+)"))
def on_admin_cancel_order_callback(client, callback_query):
    user_id = callback_query.from_user.id

    order_id = int(callback_query.data.split("_")[-1])
    order = Order.get_or_none(Order.id == order_id)

    order.delete_instance()

    admin_app.delete_messages(user_id, callback_query.message.id)

    admin_app.answer_callback_query(callback_query.id, text="Заказ удален")


# on admin_delete_message callback
@admin_app.on_callback_query(filters.regex("admin_delete_message"))
def on_admin_delete_message_callback(client, callback_query):
    user_id = callback_query.from_user.id

    admin_app.delete_messages(
        user_id,
        callback_query.message.id
    )
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin set price menu
@admin_app.on_callback_query(filters.regex("admin_set_price_(\d+)"))
def on_admin_set_price_callback(client, callback_query):
    user_id = callback_query.from_user.id

    order_id = int(callback_query.data.split("_")[-1])
    order = Order.get_or_none(Order.id == order_id)

    text = "{}| Определите цену заказа в рублях. (Не более 1000.00 рублей из-за " \
           "ограничений тестовой системы платежей.)\nПример: 449.99"
    conv_mess = admin_app.send_message(
        chat_id=user_id,
        reply_markup=types.ForceReply(selective=True, placeholder="Цена заказа"),
        text=text.format(str(order.id)),
    )

    adm_conv_dict[user_id] = ["admin_set_price", conv_mess]
    edit_admin_menu(user_id, callback_query.message.id)
    admin_app.answer_callback_query(callback_query.id, text="Принято")


# on admin back menu
@admin_app.on_callback_query(filters.regex("back"))
def on_admin_back_callback(client, callback_query):
    user_id = callback_query.from_user.id

    edit_admin_menu(user_id, callback_query.message.id)
    admin_app.answer_callback_query(callback_query.id, text="Принято")


if __name__ == "__main__":
    # Start bot_app and admin_app at the same time (async)
    bot_app.start()
    bot_p_app.start()
    admin_app.start()
    idle()
