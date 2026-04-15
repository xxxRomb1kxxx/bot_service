from aiogram.fsm.state import State, StatesGroup


class DialogState(StatesGroup):
    waiting_question = State()
    waiting_diagnosis = State()