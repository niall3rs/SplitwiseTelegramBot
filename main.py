import configurations.settings as settings
import logging
import os

from telegram.ext import Updater, CommandHandler, ConversationHandler, Dispatcher
from importlib import import_module
from splitwise_telegram import SplitwiseTelegramBot

import utils.logger as logger

BOT_TOKEN = os.environ.get("BOT_TOKEN")

splitwise = SplitwiseTelegramBot()


def load_handlers(dispatcher: Dispatcher):
    """Load handlers from files in a 'bot' directory."""
    base_path = os.path.join(os.path.dirname(__file__), 'bot')
    files = os.listdir(base_path)

    for file_name in files:
        handler_module, _ = os.path.splitext(file_name)

        module = import_module(f'.{handler_module}', 'bot')
        module.init(dispatcher)


# TODO - find some way to store the last notification id and keep a job running which will check for new notifications
def get_notifications(update, context):
    # _initialize_bot(update)

    print(splitwise.getNotifications())


def unknown(update, context):
    update.message.reply_text(text="Sorry, I didn't understand that command.")


def main():
    logger.init_logger(f'logs/{settings.NAME}.log')
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    load_handlers(updater.dispatcher)

    # # dispatcher.add_handler(CommandHandler(GET_NOTIFICATIONS, get_notifications_callback))

    # # on noncommand i.e message - echo the message on Telegram
    # dispatcher.add_handler(MessageHandler(Filters.command, unknown))

    if settings.WEBHOOK:
        # signal.signal(signal.SIGINT, graceful_exit)
        updater.start_webhook(**settings.WEBHOOK_OPTIONS)
        updater.bot.set_webhook(url=settings.WEBHOOK_URL)
    else:
        updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
