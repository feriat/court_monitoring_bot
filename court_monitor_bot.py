#!/usr/bin/python
# -*- coding: utf-8 -*-

import telegram
from telegram import Bot, ReplyKeyboardMarkup, ChatAction
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackQueryHandler, RegexHandler, ConversationHandler,
    Job
)

import botan

import datetime

from peewee import SqliteDatabase, Model, CharField, DateTimeField, \
    IntegerField, BooleanField, BigIntegerField, TextField, \
    IntegrityError

import logging

import json

import urllib3
urllib3.disable_warnings()

import time

from court import get_magistrate_court, make_url
from fake_update import FakeUpdate

logger = logging.getLogger(__name__)


# Это токен от бота
TELEGRAM_TOKEN = open('database/telegram_token').read().strip()
# Это ботан от бота
BOTAN_IO = open('database/botan_token').read().strip()


HELP_MESSAGE = u'''Этот бот умеет автоматически следить за судами
и присылать уведомления о делах против вас или ваших близких.

Проверить, работает ли бот, можно с помощью команды /check
Ввести данные о себе можно с помощью кнопок в меню.
Нажмите /start, если что-то сломалось
'''

ADMIN_CHAT_ID = None

DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

MARKDOWN = telegram.ParseMode.MARKDOWN
AWAITING_DATA = [['Фамилия', 'Номер мирового суда'],
                 ['Проверить статус судов', 'Отменить подписку'],
                 ]
FILLED = [['Проверить статус судов'],
          ['Обновить данные', 'Отменить подписку'],
          ]

AWAITING_DATA_MARKUP = ReplyKeyboardMarkup(AWAITING_DATA,
                                           one_time_keyboard=True)
FILLED_MARKUP = ReplyKeyboardMarkup(FILLED, one_time_keyboard=False)

CHOOSING, TYPING_REPLY = range(2)

DAILY = 60.0 * 60 * 24

def _now():
    return datetime.datetime.now()


class Subscriber(Model):
    chat_id = BigIntegerField(unique=True, index=True)
    first_name = CharField(default="")
    username = CharField(default="")
    created_date = DateTimeField(default=_now)
    subscription_type = IntegerField(default=0)
    is_admin = BooleanField(default=False)
    deleted = BooleanField(default=False)
    dialog_state = CharField(default="")
    # JSON object to store court info state
    court_info = CharField(default="{}")
    court_last_name = TextField(default="")
    email = TextField(default="")
    class Meta:
        database = SqliteDatabase('database/DB.db')


def botan_track(command):
    def decorator(function):
        def wrapper(*args, **kwargs):
            res = function(*args, **kwargs)
            try:
                update = args[1]
                uid = update.message.from_user.id
                message_dict = update.message.to_dict()
                #event_name = update.message.text
                botan.track(BOTAN_IO, uid, message_dict, command)
            except:
                pass 
            finally:
                return res

        return wrapper
    return decorator


def valid_court_number(text):
    try:
        court_num = int(text)
        return court_num < 1000 and court_num > 0
    except ValueError:
        return False


def check_data_completeness(bot, update, *args):
    for subscriber in Subscriber.select().where(
        Subscriber.chat_id == update.message.chat_id
    ):
        court_last_name, court_info = subscriber.court_last_name, subscriber.court_info
        court_info = json.loads(court_info or "{}")
        court_number = court_info.get('magistrate_court_num', None)
        if not court_last_name:
            return await_last_name(bot, update, *args)
        elif not court_number:
            return await_court_num(bot, update, *args)

    update.message.reply_text("Все необходимые данные заполнены! Теперь несколько "
                              "раз в сутки бот будет проверять наличие исков "
                              "против в вас, и сообщит вам при его появлении",
                              reply_markup=FILLED_MARKUP)

    return ConversationHandler.END


@botan_track('start')
def start(bot, update, user_data):
    try:
        subscriber = Subscriber.create(
            chat_id=update.message.chat_id,
            first_name=update.message.from_user.first_name,
            username=update.message.from_user.username,
        )
    except IntegrityError:
        subscriber = Subscriber.update(
            chat_id=update.message.chat_id,
            first_name=update.message.from_user.first_name,
            username=update.message.from_user.username,
            deleted=False,
        )
        subscriber.execute()
    except Exception, e:
        logger.error(e)
    bot.sendMessage(chat_id=update.message.chat_id, text=u'''Добрый день!\n\n''' + HELP_MESSAGE,
                    parse_mode=MARKDOWN, reply_markup=AWAITING_DATA_MARKUP)
    bot.sendChatAction(chat_id=update.message.chat_id,
                       action=ChatAction.TYPING)
    time.sleep(1.7)
    return check_data_completeness(bot, update, user_data)


@botan_track('help')
def help(bot, update):
    bot.sendMessage(update.message.chat_id,
                    text=HELP_MESSAGE, parse_mode=MARKDOWN)
    return CHOOSING


@botan_track('await_last_name')
def await_last_name(bot, update, user_data):
    print 'await_last_name'
    update.message.reply_text(u"Введите вашу фамилию. \n\n"
                              u"По ней будет проиходить поиск по сайтам судов. "
                              u"Чтобы уточнить поиск вы можете ввести первую букву имени, "
                              u"например `Иванов И`."
                              )
    user_data['choice'] = u'Фамилия'
    return TYPING_REPLY


@botan_track('await_court_num')
def await_court_num(bot, update, user_data):
    print 'await_court_num'
    update.message.reply_text(u"Введите номер мирового суда. \n\n"
                              u"Если вы прописаны в ЖК Богородское, ваш суд номер 110. "
                              u"Найди свой участок (в случае прописки в Москве) можно по адресу "
                              u"http://ums.mos.ru/justices/sites-of-world-judges-at-the-address/"
                              )
    user_data['choice'] = u'Номер мирового суда'
    return TYPING_REPLY


def update(bot, update, user_data):
    update.message.reply_text(u"Какие данные вы хотите обновить?",
                              reply_markup=AWAITING_DATA_MARKUP
                              )
    return CHOOSING


def received_information(bot, update, user_data):
    text = update.message.text
    chat_id = update.message.chat_id
    category = user_data['choice']
    if category == u'Фамилия':
        subscriber = Subscriber.update(
            court_last_name=text
        ).where(Subscriber.chat_id == chat_id)
        subscriber.execute()
    elif category == u'Номер мирового суда':
        if valid_court_number(text):
            court_num = int(text)
            court_info = {'magistrate_court_num': court_num}

            subscriber = Subscriber.update(
                court_info=json.dumps(court_info)
            ).where(Subscriber.chat_id == chat_id)
            subscriber.execute()
        else:
            update.message.reply_text(
                "Некорректный номер суда, попробуйте ещё раз")
            return TYPING_REPLY

    del user_data['choice']

    return check_data_completeness(bot, update, user_data)


@botan_track('court_status_check')
def court_status_check(bot, update, silent_if_fine=False):
    plaintiff = u'жилсервис'
    for subscriber in Subscriber.select().where(
        Subscriber.chat_id == update.message.chat_id
    ):
        court_last_name, court_info = subscriber.court_last_name, subscriber.court_info
        court_info = json.loads(court_info or "{}")
        court_number = court_info.get('magistrate_court_num', None)
        if not court_last_name or not court_number:
            if not silent_if_fine:
                update.message.reply_text("Не все поля заполнены: мне необходимо знать "
                                          "как минимум номер суда и вашу фамилию.")
            return

        if not silent_if_fine:
            update.message.reply_text(u"Проверяю мировой суд номер {}, ответчик `{}`, "
                                      u"истец {}".format(
                                          court_number, court_last_name, plaintiff),
                                      reply_markup=FILLED_MARKUP)
        try:
            df = get_magistrate_court(
                court='mos-sud', court_num=court_number, defendant=court_last_name, plaintiff=plaintiff
            )
            if df is not None and len(df) > 0:
                print make_url(court='mos-sud', court_num=court_number,
                               defendant=court_last_name, plaintiff=plaintiff)
                update.message.reply_text(
                    u"ВНИМАНИЕ! \n"
                    u"Найден иск против вас! \n"
                    u"Пройдите по ссылке, чтобы ознакомиться с ним. {}".format(
                        make_url(court='mos-sud', court_num=court_number,
                                 defendant=court_last_name, plaintiff=plaintiff)
                    ),
                    reply_markup=FILLED_MARKUP)
            elif not silent_if_fine:
                update.message.reply_text(
                    u"Исков не найдено, отлично! \n"
                    u"Убедиться в этом можно по ссылке: {}".format(
                        make_url(court='mos-sud', court_num=court_number,
                                 defendant=court_last_name, plaintiff=plaintiff)
                    ),
                    reply_markup=FILLED_MARKUP)
        except ValueError, e:
            print e
            raise
            if not silent_if_fine:
                update.message.reply_text(
                    u"Указанная фамилия `{}` или номер суда `{}` не подходят к формату сайта суда. "
                    u"Проверьте, нет ли ошибки, и упростите: используйте только цифры для номера суда, "
                    u"только кирилические буквы для фамилии.".format(
                        court_last_name, court_number
                    ),
                    reply_markup=FILLED_MARKUP)

    return ConversationHandler.END


def cron_check(bot, job):
    for subscriber in Subscriber.select().where(
        Subscriber.deleted == False
    ):
        try:
            update = FakeUpdate(bot, subscriber.chat_id)
            court_status_check(bot, update, silent_if_fine=True)
        except Exception, e:
            print e
            continue


@botan_track('unsubscribe')
def unsubscribe(bot, update):
    try:
        subscriber = Subscriber.update(deleted=True).where(
            Subscriber.chat_id == update.message.chat_id)
        subscriber.execute()
        bot.sendMessage(update.message.chat_id,
                        text='Подписка удалена успешно, спасибо, что проявили интерес!'
                             ' Чтобы возобновить подписку, воспользуйтесь командой /start')
    except:
        bot.sendMessage(update.message.chat_id,
                        text='ERROR occured, action NOT executed. See console output!')
        print update
        raise


def test(bot, update, user_data):
    print update


def status(bot, update):
    print update
    bot.sendMessage(update.message.chat_id,
                    text='{0}'.format(update.message.chat_id))


def error(bot, update, error):
    logger.error('Update "%s" caused error "%s"' % (update, error))
    # bot.sendMessage(ADMIN_CHAT_ID, text='Update "%s" caused error "%s"' % (update, error))


def main():
    # Create the EventHandler and pass it your bot's token.
    # updater = Updater(TELEGRAM_TOKEN, workers=5)
    updater = Updater(TELEGRAM_TOKEN)
    job_queue = updater.job_queue

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # dp.add_handler(CommandHandler('test', test))
    # dp.add_handler(CommandHandler('help', help))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start, pass_user_data=True),
                      RegexHandler(u'^Обновить данные$',
                                   update,
                                   pass_user_data=True),
                      RegexHandler(u'^Фамилия$',
                                   await_last_name,
                                   pass_user_data=True),
                      RegexHandler(u'^Номер мирового суда$',
                                   await_court_num,
                                   pass_user_data=True),
                      ],

        states={
            CHOOSING: [RegexHandler(u'^Фамилия$',
                                    await_last_name,
                                    pass_user_data=True),
                       RegexHandler(u'^Номер мирового суда$',
                                    await_court_num,
                                    pass_user_data=True),
                       ],

            TYPING_REPLY: [MessageHandler(Filters.text,
                                          received_information,
                                          pass_user_data=True),
                           ],
        },

        fallbacks=[RegexHandler(
            u'^Проверить статус судов$', court_status_check)]
    )

    dp.add_handler(conv_handler)
    dp.add_handler(RegexHandler(
        u'^Проверить статус судов$', court_status_check))
    dp.add_handler(RegexHandler(u'^Отменить подписку$', unsubscribe))
    dp.add_handler(CommandHandler('status', status))

    # Add daily court check
    job_minute = Job(cron_check, DAILY)
    job_queue.put(job_minute, next_t=0)

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until the you presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':

    # Enable logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    main()
