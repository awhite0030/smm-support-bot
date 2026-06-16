from . import command
from . import message
from . import callback

routers = [
    command.router,
    command.router_id,
    message.router,
    callback.router,
]
