import logging

from functools import wraps
from splitwise import Splitwise
from splitwise.expense import Expense
from splitwise.user import ExpenseUser
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, Filters
from config import BOT_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET
from commands import HELP, LIST_EXPENSE, SETTLE_EXPENESE, CREATE_EXPENSE, GET_NOTIFICATIONS, START, CONNECT, CANCEL

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

splitwise_object = Splitwise(CONSUMER_KEY, CONSUMER_SECRET)

SETTLE_WITH_FRIEND = 'settle_with_friend'

commands = {
    LIST_EXPENSE: 'List expenses from your Splitwise account',
    SETTLE_EXPENESE: 'Settle expenses in your Splitwise account'
}

SETTLE_WITH, CONFIRM = range(2)


# OAUTH_TOKEN, OAUTH_TOKEN_SECRET = None, None


def connect(update, context):
    url, secret = splitwise_object.getAuthorizeURL()
    context.chat_data['secret'] = secret
    update.message.reply_text(url)


def start(update, context):
    logger.info(context.args[0])
    global OAUTH_TOKEN, OAUTH_TOKEN_SECRET
    tokens = context.args[0].split('-')
    OAUTH_TOKEN = tokens[0]
    OAUTH_TOKEN_SECRET = tokens[1]
    logger.info(context.chat_data['secret'])
    access_token = splitwise_object.getAccessToken(OAUTH_TOKEN, context.chat_data['secret'], OAUTH_TOKEN_SECRET)
    logger.info(
        access_token)  # dictionary with oauth_token and oauth_token_secret as keys, these are the real values for login purposes
    splitwise_object.setAccessToken(access_token)


def help(update, context):
    help_text = 'The following commands are available: \n'
    help_text += ''.join([f"{command}: {commands[command]}\n" for command in commands])
    update.message.reply_text(help_text)  # send the generated help page


def send_typing_action(func):
    """Sends typing action while processing func command."""

    @wraps(func)
    def command_func(update, context, *args, **kwargs):
        context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)
        return func(update, context, *args, **kwargs)

    return command_func


def initialize_bot(update):
    """ initialize the splitwise object """
    if update is not None:
        logger.info('User %s started the conversation.', update.message.from_user.first_name)
    access_token = {
        'oauth_token': OAUTH_TOKEN,
        'oauth_token_secret': OAUTH_TOKEN_SECRET
    }
    splitwise_object.setAccessToken(access_token)
    logger.info('Splitwise Bot initalized!')


def _get_amount_from_friend(friend):
    return abs(float(friend.getBalances()[0].getAmount()))


def _get_lend_expenses(friends_with_expenses):
    lend_output = 'OWES YOU:\n'
    lend_output += ''.join(
        [f'{friend.getFirstName()} {friend.getLastName()}: ₹{_get_amount_from_friend(friend)}\n'
         for friend in friends_with_expenses if float(friend.getBalances()[0].getAmount()) > 0])
    logger.debug(lend_output)
    return lend_output


def _get_borrowed_expenses(friends_with_expenses):
    borrow_output = 'YOU OWE:\n'
    borrow_output += ''.join(
        [f'{friend.getFirstName()} {friend.getLastName()}: ₹{_get_amount_from_friend(friend)}\n'
         for friend in friends_with_expenses if float(friend.getBalances()[0].getAmount()) < 0])
    logger.debug(borrow_output)
    return borrow_output


def _get_friends_with_expenses():
    friends_with_expenses = [friend for friend in splitwise_object.getFriends() if len(friend.getBalances()) > 0]
    logger.debug(friends_with_expenses)
    return friends_with_expenses


def _get_all_expenses():
    friends_with_expenses = _get_friends_with_expenses()
    output = _get_lend_expenses(friends_with_expenses) + '\n\n' + _get_borrowed_expenses(friends_with_expenses)
    return output


@send_typing_action
def list_expense(update, context):
    initialize_bot(update)
    output = _get_all_expenses()
    update.message.reply_text(output)


def _get_keyboard_layout(context):
    friends_with_expenses = _get_friends_with_expenses()
    borrowed_friends = [friend for friend in friends_with_expenses if float(friend.getBalances()[0].getAmount()) < 0]

    keyboard = []
    row = []
    for friend in borrowed_friends:
        name = f'{friend.getFirstName()}  {friend.getLastName()}'
        row.append(InlineKeyboardButton(name, callback_data=friend.getId()))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    keyboard.append(row)
    return keyboard


def settle_expense(update, context):
    initialize_bot(update)
    reply_markup = InlineKeyboardMarkup(_get_keyboard_layout(context))
    update.message.reply_text(
        'Settle with',
        reply_markup=reply_markup
    )
    return SETTLE_WITH


def settle_with_friend(update, context):
    query = update.callback_query
    friend_id = int(query.data)
    friends = _get_friends_with_expenses()

    _id_name_mapping = {friend.getId(): f'{friend.getFirstName()} {friend.getLastName()}' for friend in friends}
    _id_amount_mapping = {friend.getId(): _get_amount_from_friend(friend)    for friend in friends}

    # logger.info(_id_name_mapping[friend_id], _id_amount_mapping[friend_id])
    context.chat_data[SETTLE_WITH_FRIEND] = (_id_name_mapping[friend_id], _id_amount_mapping[friend_id], friend_id)
    confirm_settlement(update, context)
    return CONFIRM


def confirm_settlement(update, context):
    query = update.callback_query
    name, amount, _ = context.chat_data[SETTLE_WITH_FRIEND]
    keyboard = [
        [InlineKeyboardButton('Yes', callback_data='yes'),
         InlineKeyboardButton('No', callback_data='no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text=f'Settle balance with {name} of ₹{amount}?',
        reply_markup=reply_markup
    )


def create_settlement(update, context):
    logger.info("Settling the expense!")
    query = update.callback_query

    name, amount, friend_id = context.chat_data[SETTLE_WITH_FRIEND]

    self_id = splitwise_object.getCurrentUser().getId()

    expense = Expense()
    expense.setCost(amount)
    expense.setDescription('Settling the amount')

    payer = ExpenseUser()
    payer.setId(self_id)
    payer.setPaidShare(amount)
    payer.setOwedShare(0.00)

    payee = ExpenseUser()
    payee.setId(friend_id)
    payee.setPaidShare(0.00)
    payee.setOwedShare(amount)

    users = [payer, payee]
    expense.setUsers(users)
    expense = splitwise_object.createExpense(expense)

    logger.info(expense)
    context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text='Expense settled!'
    )


def cancel_settlement(update, context):
    query = update.callback_query
    context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text='No settlement done'
    )


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


# TODO - find some way to store the last notification id and keep a job running which will check for new notifications
def get_notifications(update, context):
    initialize_bot(update)
    print(splitwise_object.getNotifications())


def unknown(update, context):
    update.message.reply_text(text="Sorry, I didn't understand that command.")


def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler(CONNECT, connect))
    dispatcher.add_handler(CommandHandler(START, start))
    dispatcher.add_handler(CommandHandler(HELP, help))
    dispatcher.add_handler(CommandHandler(LIST_EXPENSE, list_expense))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler(SETTLE_EXPENESE, settle_expense)],
        states={
            SETTLE_WITH: [CallbackQueryHandler(settle_with_friend)],
            CONFIRM: [
                CallbackQueryHandler(create_settlement, pattern='^yes$'),
                CallbackQueryHandler(cancel_settlement, pattern='^no$')
            ]
        },
        fallbacks=[CommandHandler(CANCEL, cancel_settlement)],
        allow_reentry=True,
        conversation_timeout=180,

    )
    dispatcher.add_handler(conv_handler)

    # dispatcher.add_handler(CommandHandler(GET_NOTIFICATIONS, get_notifications_callback))
    # dispatcher.add_handler(CommandHandler(SETTLE_EXPENESE, settle_expense_callback))

    # on noncommand i.e message - echo the message on Telegram
    dispatcher.add_handler(MessageHandler(Filters.command, unknown))

    # log all errors
    dispatcher.add_error_handler(error)

    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
