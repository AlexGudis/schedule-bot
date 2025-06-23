"""Handlers for our bot."""
import asyncio
import pytz
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types.inline_keyboard_button import InlineKeyboardButton
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.filters import CommandStart, Command, CommandObject, StateFilter
# from aiogram.filters.command import Command
import supabase as sb

from config_reader import config

from aiogram import F, Router


router = Router()

URL = config.url.get_secret_value()
KEY = config.key.get_secret_value()

CLIENT = sb.create_client(URL, KEY)
moscow_tz = pytz.timezone("Europe/Moscow")


class Registration(StatesGroup):
    """Fields to be complited during registartion."""

    name = State()
    passed = State()


class HomeWork(StatesGroup):
    """Field to be complited during homework creation."""

    choosing_action = State()  # Пользователь выбирает, что он хочет сделать: посмотреть текущие ДЗ или добавить новые
    selecting_subject = State()  # Пользователь решил добавить новое ДЗ, тогда ему надо выбрать предмет из имеющихся
    entering_task = State()  # Нужно добавить описание нового ДЗ
    entering_deadline = State()  # Нужно ввести дату дедлайна
    viewing_homeworks = State()  # Пользователь хочет посмотреть текущие ДЗ


class AddDeadline(StatesGroup):
    """States for cgreating new deadlines."""

    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_title = State()


@router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    """Greeting of the bot."""
    registration = InlineKeyboardBuilder()
    registration.add(InlineKeyboardButton(
        text="Регистрация",
        callback_data="registration")
    )
    await message.answer("Привет! Я бот 321 группы. Для начала необходимо зарегестрироваться.",
                         reply_markup=registration.as_markup())


@router.callback_query(F.data == 'registration')
async def registration(callback: CallbackQuery, state: FSMContext):
    """Start of registartion."""
    print(str(callback.from_user.username))
    same_user = CLIENT.table("users").select("*").eq("tg_username", str(callback.from_user.username)).execute().data
    if same_user:
        check = InlineKeyboardBuilder()
        check.add(InlineKeyboardButton(
            text="Всё верно",
            callback_data='right'
        ))
        check.add(InlineKeyboardButton(
            text='Редактировать',
            callback_data='fix'
        ))
        await callback.message.answer(f"Вы уже зарегестрированы со следующими данными.\n\nФИО: {same_user[0]['name']}",
                                      reply_markup=check.as_markup())
        return
    await callback.message.answer('Введите ваше ФИО:')
    await state.set_state(Registration.name)


@router.callback_query(F.data == 'fix')
async def fix_registration(callback: CallbackQuery, state: FSMContext):
    """Start registration from the beginning."""
    CLIENT.table("users").delete().eq("tg_username", str(callback.from_user.username)).execute()
    await callback.message.answer('Введите ваше ФИО:')
    await state.set_state(Registration.name)


@router.message(F.text, Registration.name)
async def process_name(message: Message, state: FSMContext):
    """Add user."""
    CLIENT.table("users").insert({"tg_id": str(message.from_user.id),
                                  "name": message.text,
                                  "tg_username": message.from_user.username}).execute()
    await message.answer("Отлично!")
    await state.clear()


@router.callback_query(F.data == 'right')
async def wait(callback: CallbackQuery, state: FSMContext):
    """Standart response."""
    tg_id, tg_username = str(callback.from_user.id), str(callback.from_user.username)
    CLIENT.table("users").update({"tg_id": tg_id}).eq("tg_username", tg_username).execute()
    await callback.message.answer('Отлично!')
    await state.set_state(Registration.passed)


@router.message(StateFilter(Registration.passed), Command("hw"))
async def homework_menu(message: Message, state: FSMContext):
    """Start of hw command. Chose between add and check homework."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить ДЗ", callback_data="add_hw")],
        [InlineKeyboardButton(text="Посмотреть ДЗ", callback_data="view_hw")]
    ])
    await message.answer("Выберите действие:", reply_markup=keyboard)
    await state.set_state(HomeWork.choosing_action)


@router.callback_query(HomeWork.choosing_action, F.data == "add_hw")
async def action_selected(callback: CallbackQuery, state: FSMContext):
    """Adding hw selected. Choose subject to add hw."""
    await callback.answer()
    # action = callback.data

    response = CLIENT.table('subjects').select('id, name').execute()
    subjects = response.data

    if not subjects:
        await callback.message.answer("В базе нет предметов.")
        return await state.clear()

    builder = InlineKeyboardBuilder()
    for subj in subjects:
        builder.button(text=subj['name'], callback_data=f"subject_{subj['id']}")

    builder.adjust(2)
    await callback.message.answer("Выберите предмет:", reply_markup=builder.as_markup())

    await state.set_state(HomeWork.selecting_subject)
    await callback.answer()


@router.callback_query(HomeWork.selecting_subject)
async def subject_selected(callback: CallbackQuery, state: FSMContext):
    """Insert hw description of a chosen subject."""
    # print(f'DATA = {callback.data}')
    subject_id = int(callback.data.split("_")[-1])
    await state.update_data(subject_id=subject_id)

    try:
        response = CLIENT.table('subjects').select('name').eq('id', subject_id).execute()
        subject_name = response.data[0]['name'] if response.data else "неизвестный предмет"

        await callback.message.answer(f"Выбран предмет: {subject_name}\n")
        await callback.message.answer("Введите задание:")
        await state.set_state(HomeWork.entering_task)

    except Exception as e:
        await callback.message.answer("Ошибка при получении данных о предмете")
        print(f"Error getting subject name: {e}")
        await state.clear()

    await callback.answer()


@router.message(HomeWork.entering_task)
async def task_entered(message: Message, state: FSMContext):
    """Insert deadline of the hw."""
    await state.update_data(task=message.text)
    await message.answer("Введите дедлайн в формате ДД.ММ.ГГГГ")
    await state.set_state(HomeWork.entering_deadline)


@router.message(HomeWork.entering_deadline)
async def deadline_entered(message: Message, state: FSMContext):
    """Insert hw into BD."""
    try:
        deadline = datetime.strptime(message.text, "%d.%m.%Y").date()
        if deadline < datetime.now().date():
            await message.answer("Дедлайн не может быть в прошлом! Введите корректную дату:")
            return

        data = await state.get_data()

        # print(f'DATA_INSERT = subject_id: {int(data['subject_id'])},task: \
        # {str(data['task'])}, deadline: {deadline.isoformat()}, user_id: {str(message.from_user.id)}')

        CLIENT.table('homework').insert({'subject_id': int(data['subject_id']), 'description': str(data['task']),
                                         'due_date': deadline.isoformat(),
                                         'is_completed': False,
                                         'tg_id': str(message.from_user.id)}).execute()

        await message.answer("ДЗ успешно добавлено!")
        # После добавления ДЗ возвращаемся в начальное состояние. Пользователь зареган и может давать команды
        await state.set_state(Registration.passed)

    except ValueError:
        await message.answer("Неверный формат даты! Введите в формате ДД.ММ.ГГГГ:")


@router.callback_query(HomeWork.choosing_action, F.data == "view_hw")
async def view_homeworks_start(callback: CallbackQuery, state: FSMContext):
    """Choose subject."""
    try:
        response = CLIENT.table('subjects').select('id, name').execute()
        subjects = response.data

        if not subjects:
            await callback.message.answer("В базе нет предметов.")
            return await state.clear()

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=subj['name'], callback_data=f"view_subject_{subj['id']}")]
                for subj in subjects])

        await callback.message.answer("Выберите предмет для просмотра ДЗ:", reply_markup=keyboard)
        await state.set_state(HomeWork.viewing_homeworks)
        await callback.answer()

    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")
        await state.set_state(Registration.passed)


@router.callback_query(HomeWork.viewing_homeworks, F.data.startswith("view_subject_"))
async def show_homeworks(callback: CallbackQuery, state: FSMContext):
    """Get hw for particular subject."""
    subject_id = callback.data.split("_")[-1]

    try:
        subject_name = CLIENT.table('subjects').select('name').eq('id', subject_id).execute().data[0]['name']

        homeworks = CLIENT.table('homework').select('description, due_date').eq(
            'subject_id', subject_id).order('due_date').execute().data

        if not homeworks:
            await callback.message.answer(f"По предмету {subject_name} нет домашних заданий.")
        else:
            hw_list = "\n\n".join(f"Описание задания: {hw['description']}\n"
                                  f"Дедлайн: {datetime.fromisoformat(hw['due_date']).strftime('%d.%m.%Y')}"
                                  for hw in homeworks)

            await callback.message.answer(f"Домашние задания по предмету {subject_name}:\n\n{hw_list}")

        await state.set_state(Registration.passed)
        await callback.answer()
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")
        await state.set_state(Registration.passed)


@router.message(F.text, Command("schedule"))
async def set_day(message: Message, state: FSMContext):
    """Select day to get schedule."""
    day = InlineKeyboardBuilder()
    day.add(InlineKeyboardButton(
        text="Понедельник",
        callback_data="monday")
    )
    day.add(InlineKeyboardButton(
        text="Вторник",
        callback_data="tuesday")
    )
    day.add(InlineKeyboardButton(
        text="Среда",
        callback_data="wednesday")
    )
    day.add(InlineKeyboardButton(
        text="Четверг",
        callback_data="thursday")
    )
    day.add(InlineKeyboardButton(
        text="Пятница",
        callback_data="friday")
    )
    day.adjust(1)
    await message.answer("Выбери день недели",
                         reply_markup=day.as_markup())


def get_schedule(day, day_to_print):
    """Get all information to print schedule."""
    schedule = CLIENT.table("schedule").select("*").eq("day_of_week", day).execute().data
    if not schedule:
        return 'В этот день нет пар.'
    mes = '<b>Расписание на {}</b>'.format(day_to_print)
    schedule = sorted(schedule, key=lambda x: x['pair_number'])
    for i in schedule:
        classroom = CLIENT.table('classrooms').select('number').eq("id", i["classroom_id"]).execute().data
        time = CLIENT.table('time_slots').select('*').eq("pair_number", i["pair_number"]).execute().data
        if i["teacher_id"]:
            teacher = CLIENT.table('teachers').select('*').eq("id", i["teacher_id"]).execute().data
        else:
            teacher = ''
        match i['week_type']:
            case 'even':
                week_type = ' чётные недели'
            case 'odd':
                week_type = ' нечётные недели'
            case _:
                week_type = ''
        mes += f"\n\n<b>{time[0]['start_time'][:-3]} - {time[0]['end_time'][:-3]}</b>" + week_type
        mes += "\nПредмет: <b>{}</b>".format(i['subject'])
        mes += "\nКабинет: <b>{}</b>".format(classroom[0]['number'])
        if teacher:
            mes += "\nПреподаватель: {}".format(teacher[0]['name'])
    return mes


@router.callback_query(F.data == 'monday')
async def monday(callback: CallbackQuery, state: FSMContext):
    """Schedule for monday."""
    schedule = get_schedule(1, 'понедельник')
    await callback.message.answer(schedule, parse_mode="HTML")


@router.callback_query(F.data == 'tuesday')
async def tuesday(callback: CallbackQuery, state: FSMContext):
    """Schedule for tuesday."""
    schedule = get_schedule(2, 'вторник')
    await callback.message.answer(schedule, parse_mode="HTML")


@router.callback_query(F.data == 'wednesday')
async def wednesday(callback: CallbackQuery, state: FSMContext):
    """Schedule for wednesday."""
    schedule = get_schedule(3, 'среда')
    await callback.message.answer(schedule, parse_mode="HTML")


@router.callback_query(F.data == 'thursday')
async def thursday(callback: CallbackQuery, state: FSMContext):
    """Schedule for thursday."""
    schedule = get_schedule(4, 'четверг')
    await callback.message.answer(schedule, parse_mode="HTML")


@router.callback_query(F.data == 'friday')
async def friday(callback: CallbackQuery, state: FSMContext):
    """Schedule for friday."""
    schedule = get_schedule(5, 'пятница')
    await callback.message.answer(schedule)


@router.message(F.text, Command("help"))
async def get_help(message: Message, state: FSMContext):
    """Print all commands with instruction."""
    await message.answer(
        "/schedule - просмотр расписания,\n"
        "/deadlines - добавить/просмотреть дедлайны\n"
        "/hw - домашнее задание"
    )


@router.message(Command("deadlines"))
async def cmd_deadline(message: Message, command: CommandObject):
    """Options to work with deadlines."""
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(text="Создать", callback_data="create"),
        InlineKeyboardButton(text="Посмотреть список", callback_data="check_list"),
    )

    await message.answer(
        "Здесь можно настроить или узнать текущие дедлайны. Выберите действие:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data == "create")
async def start_add_deadline(callback: CallbackQuery, state: FSMContext):
    """Create new deadline."""
    await callback.message.edit_text("Введите дату дедлайна в формате YYYY-MM-DD")
    await state.set_state(AddDeadline.waiting_for_date)


@router.message(AddDeadline.waiting_for_date)
async def input_date(message: Message, state: FSMContext):
    """Input deadline date."""
    try:
        date = datetime.strptime(message.text, "%Y-%m-%d").date()
        await state.update_data(date=date)
        await message.answer("Теперь введите время дедлайна в формате HH:MM")
        await state.set_state(AddDeadline.waiting_for_time)
    except ValueError:
        await message.answer("Неверный формат. Введите дату как YYYY-MM-DD")


@router.message(AddDeadline.waiting_for_time)
async def input_time(message: Message, state: FSMContext):
    """Input deadline time."""
    try:
        time = datetime.strptime(message.text, "%H:%M").time()
        await state.update_data(time=time)
        await message.answer("Теперь введите название дедлайна")
        await state.set_state(AddDeadline.waiting_for_title)
    except ValueError:
        await message.answer("Неверный формат. Введите время как HH:MM")


@router.message(AddDeadline.waiting_for_title)
async def input_title(message: Message, state: FSMContext):
    """Input deadline title."""
    user_data = await state.get_data()
    title = message.text

    naive_dt = datetime.combine(user_data["date"], user_data["time"])
    moscow_dt = moscow_tz.localize(naive_dt)

    CLIENT.table("deadlines").insert({
        "telegram_id": message.from_user.id,
        "title": title,
        "deadline_at": moscow_dt.isoformat(),
        "notified": False
    }).execute()

    await message.answer(f"Дедлайн «{title}» добавлен на {moscow_dt.strftime('%d.%m.%Y %H:%M')} (МСК)")
    await state.clear()


@router.callback_query(F.data == "check_list")
async def check_deadlines_list(callback: CallbackQuery, state: FSMContext):
    """Check all deadlines."""
    user_id = callback.from_user.id
    now = datetime.now(pytz.UTC)
    future_deadlines = CLIENT.table("deadlines").select(
        "*").eq("telegram_id", user_id).gt("deadline_at", now.isoformat()).execute()
    if not future_deadlines:
        await callback.message.answer("У вас пока нет активных дедлайнов!")
        return

    sorted_deadlines = sorted(
        future_deadlines.data,
        key=lambda x: datetime.fromisoformat(x['deadline_at'])
    )

    text = "<b>Ваши дедлайны:</b>\n\n"
    for i, deadline in enumerate(sorted_deadlines, 1):
        print(deadline)
        deadline_time = datetime.fromisoformat(deadline["deadline_at"]).strftime('%d.%m.%Y в %H:%M')
        text += (
            f"{i}. <b>{deadline['title']}</b>\n"
            f"   └ {deadline_time}\n\n"
        )

    await callback.message.answer(text, parse_mode="HTML")
