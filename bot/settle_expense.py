# Telegram API framework core imports
from telegram import InlineKeyboardMarkup
# Telegram API framework handlers imports
from telegram.ext import CommandHandler, ConversationHandler
from telegram.ext import Dispatcher, CallbackQueryHandler, Filters, MessageHandler

from main import splitwise
from utils.constants import ACCESS_TOKEN, SETTLE_EXPENSE, STATE_COMPLETE
from utils.helper import get_keyboard_layout, confirm, timeout, done, send_account_not_connected
# Helper methods import
from utils.logger import get_logger

# Init logger
logger = get_logger(__name__)

TAKE_FRIEND_INPUT, CONFIRM = range(2)


def cancel_settle_expense(update, context):
    logger.info(
        f"APP: {update.effective_user.username}: Canceling settle expense")
    query = update.callback_query
    context.user_data[STATE_COMPLETE] = True
    context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text='No expense settled'
    )


def init(dispatcher: Dispatcher):
    """Provide handlers initialization."""
    settle_handler = ConversationHandler(
        entry_points=[CommandHandler('settle_expense', settle_expense)],
        states={
            TAKE_FRIEND_INPUT: [CallbackQueryHandler(take_friend_input)],
            CONFIRM: [
                CallbackQueryHandler(create_settlement, pattern='^yes$'),
                CallbackQueryHandler(cancel_settle_expense, pattern='^no$')
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(Filters.text | Filters.command, timeout)],
        },
        fallbacks=[MessageHandler(Filters.text | Filters.command, done)],
        allow_reentry=True,
        conversation_timeout=30
    )
    dispatcher.add_handler(settle_handler, 1)


def settle_expense(update, context):
    try:
        if ACCESS_TOKEN not in context.user_data:
            raise Exception
        splitwise.setAccessToken(context.user_data[ACCESS_TOKEN])
        logger.info(
            f"APP: {update.effective_user.username}: Starting settle expense")
        friends_with_expenses = splitwise.get_friends_with_expenses()
        borrowed_friends = [friend for friend in friends_with_expenses if float(
            friend.getBalances()[0].getAmount()) < 0]
        reply_markup = InlineKeyboardMarkup(
            get_keyboard_layout(splitwise,  borrowed_friends))

        update.message.reply_text(
            'Settle with',
            reply_markup=reply_markup
        )
        return TAKE_FRIEND_INPUT
    except Exception:
        send_account_not_connected(update, context)


def take_friend_input(update, context):
    logger.info(
        f"APP: {update.effective_user.username}: Taking friend input for settle expense")
    query = update.callback_query
    friend_id = int(query.data)

    _id_name_mapping = splitwise.get_id_name_mapping()
    _id_amount_mapping = splitwise.get_id_amount_mapping()

    name = _id_name_mapping[friend_id]
    amount = _id_amount_mapping[friend_id]

    context.user_data[SETTLE_EXPENSE] = [name, amount, friend_id]

    text = f'Settle balance with {name} of ₹{amount}?'
    confirm(update, context, text, False)
    return CONFIRM


def create_settlement(update, context):
    logger.info(
        f"APP: {update.effective_user.username}: Creating settle expense")
    logger.info("Settling the expense!")
    query = update.callback_query
    name, amount, friend_id = context.user_data[SETTLE_EXPENSE]

    self_id = splitwise.getCurrentUser().getId()
    splitwise.create_expense_object(
        self_id, friend_id, amount, 'Settling the expense'
    )
    context.user_data[STATE_COMPLETE] = True
    context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text='Expense settled!'
    )
