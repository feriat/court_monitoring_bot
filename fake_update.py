#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
It's a fake module to pass the update object to the same commandhandler
that is used for the regular command
'''
class Dummy:
    pass
 
class FakeUpdate:
    def __init__(self, bot, chat_id):
        self.message = Dummy()
        self.message.chat_id = chat_id
        self.message.from_user = Dummy()
        self.message.from_user.id = None
        self.message.to_dict = lambda *args, **kwargs: {}
        self.message.reply_text = lambda text, **kwargs: bot.send_message(text=text, chat_id=chat_id, **kwargs)
