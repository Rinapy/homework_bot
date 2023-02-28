import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

from exceptions import APIAnswerError, SendMessageError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] -- %(message)s',
    handlers=[
        logging.FileHandler("my_log.log", mode='w'),
        stream_handler],
)


def send_message(bot, message):
    """Отправка сообщения в телеграм."""
    try:
        logging.debug(f"Попытка отправть сообщение - {message}")
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logging.debug('Сообщение отправлено')
    except telegram.TelegramError:
        message_error = 'Сбой при отправке сообщения в Telegram'
        logging.error(
            message_error,
            exc_info=True)
        raise SendMessageError(message_error)


def get_api_answer(current_timestamp):
    """Получение ответа от API."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except requests.exceptions.RequestException:
        message_error = (
            f'Ошибка при запросе к эндпоинту: {ENDPOINT},'
            f'параметры запроса: {params}'
        ) 
        logging.error(message_error)
        raise APIAnswerError(message_error)
    if response.status_code != 200:
        message_error = (
            'Ответ от эндпоинта отличный от 200'
            f'Эндпоинт: {ENDPOINT}, Параметры: {params},'
            f'Ответ: {response.status_code}'
        )
        logging.error(message_error)
        raise APIAnswerError(message_error)
    return response.json()


def check_response(response):
    """Проверка ответа."""
    if not isinstance(response, dict):
        message_error = f'Тип ответа API - не словарь: {response}'
        logging.error(message_error)
        raise TypeError(message_error)
    if 'homeworks' not in response:
        message_error = (
            f'Отсутствует ключ homeworks в ответе API: {response}'
        )
        logging.error(message_error)
        raise KeyError(message_error)
    if not isinstance(response['homeworks'], list):
        message_error = f'Тип ответа API - не список: {response}'
        logging.error(message_error)
        raise TypeError(message_error)
    homeworks = response['homeworks']
    try:
        homeworks[0]
    except IndexError:
        logging.debug('Нет новых статусов домашек')
    return homeworks


def parse_status(homework):
    """Получение статуса домашней работы."""
    if ('homework_name' or 'status') not in homework:
        message_error = ('Отсутству необходимые ключи'
                         ' "homework_name", "status"' )
        logging.error(message_error)
        raise KeyError(message_error)
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        message_error = (
            'Недокументированный статус домашней работы обнаружен'
            ' в ответе API'
        )
        logging.error(message_error)
        raise KeyError(message_error)
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка указаны ли все токены."""
    env_vars = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID}
    none_env_vars = [
        env_var_name
        for env_var_name, env_var in env_vars.items()
        if env_var is None
    ]
    if none_env_vars:
        logging.critical(
            f'Отсутствие обязательных переменных окружения во '
            f'время запуска бота: {", ".join(none_env_vars)}'
        )
        return False
    return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit('Проверьте, заданы ли все токены')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    prev_message = ''

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            current_timestamp = response.get(
                'current_date',
                current_timestamp
            )
            if homeworks:
                message = parse_status(homeworks[0])
                if message != prev_message:
                    prev_message = message
                    send_message(bot, message)

        except SendMessageError:
            logging.error('Сбой при отправке сообщения в Telegram')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if message != prev_message:
                prev_message = message
                logging.error(message)
                send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
