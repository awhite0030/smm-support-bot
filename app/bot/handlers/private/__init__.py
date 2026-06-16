from . import callback_query
from . import command
from . import extras
from . import message
from . import my_chat_member

routers = [
    extras.router,
    command.router,
    message.router,
    callback_query.router,
    my_chat_member.router,
]
