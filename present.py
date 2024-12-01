import logging
import sqlite3
from keep_alive import run
from telegram import Update
from telegram.ext import (
            ApplicationBuilder,
            CommandHandler,
            MessageHandler,
            filters,
            ContextTypes,
            ConversationHandler,
        )

        # Включаем логирование
logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO)

        # Указываем токен вашего бота
TOKEN = '7769564092:AAFoYInPOP3W7mMKrK1LRdLdYBl4PqwKU40'  # Замените на ваш токен
admin_chat_id = 6715030024  # Замените на ID вашего чата, если нужно

        # Создаем или открываем базу данных
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

        # Создаем таблицы, если их еще нет
cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            request_count INTEGER DEFAULT 0  -- Количество запросов
        )
        ''')
cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            price INTEGER,
            status TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
conn.commit()

        # Определяем состояния
GET_NAME, CHOOSE_TOPIC, CHOOSE_PAYMENT, CHOOSE_PAYMENT_WAITING, WAIT_FOR_ADMIN_CONFIRMATION = range(5)

        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
            user_id = update.effective_user.id

            # Проверяем, существует ли пользователь
            cursor.execute('SELECT name FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            if result:
                await update.message.reply_text(f'Привет, {result[0]}! Пожалуйста, выберите: "История" или "Общество".')
                return CHOOSE_TOPIC
            else:
                await update.message.reply_text('Привет! Пожалуйста, введите ваше имя:')
                return GET_NAME

        async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
            name = update.message.text
            user_id = update.effective_user.id

            cursor.execute('INSERT INTO users (user_id, name) VALUES (?, ?)',
                           (user_id, name))
            conn.commit()
            await update.message.reply_text('Спасибо! Выберите: "История" или "Общество".')
            return CHOOSE_TOPIC

        async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
            topic = update.message.text.lower()

            if topic in ['история', 'общество']:
                context.user_data['topic'] = topic

                # Устанавливаем цену в зависимости от количества запросов
                user_id = update.effective_user.id
                cursor.execute('SELECT request_count FROM users WHERE user_id = ?', (user_id,))
                request_count = cursor.fetchone()[0]

                price = 50 if request_count == 0 else 100  # Первая цена - 50 рублей, дальше - 100 рублей
                context.user_data['price'] = price

                await update.message.reply_text(f'Вы выбрали {topic}. Теперь выберите способ оплаты: наличные или перевод.')
                return CHOOSE_PAYMENT
            else:
                await update.message.reply_text('Пожалуйста, выберите "История" или "Общество".')
                return CHOOSE_TOPIC

        async def choose_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
            payment_method = update.message.text.lower()
            if payment_method in ['наличные', 'перевод']:
                user_id = update.effective_user.id
                cursor.execute('SELECT name FROM users WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                        price = context.user_data['price']  # Получаем цену из user_data
                        context.user_data['payment_method'] = payment_method

                        await update.message.reply_text(
                            f'Реквизиты:\nИмя: {result[0]}\nЦена: {price} рублей. Напишите "Готово", когда будете готовы сделать оплату.'
                        )

                        return CHOOSE_PAYMENT_WAITING  # Переход к состоянию ожидания "Готово"
                    else:
                        await update.message.reply_text('Пожалуйста, выберите "наличные" или "перевод".')
                        return CHOOSE_PAYMENT

                async def waiting_for_payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
                    text = update.message.text.lower()

                    if text == "готово":
                        await update.message.reply_text('Пожалуйста, подождите подтверждения оплаты...')

                        user_id = update.effective_user.id
                        cursor.execute('SELECT name FROM users WHERE user_id = ?', (user_id,))
                        result = cursor.fetchone()

                        # Добавляем запись о транзакции
                        cursor.execute('INSERT INTO transactions (user_id, name, price, status) VALUES (?, ?, ?, ?)',
                                       (user_id, result[0], context.user_data['price'], 'ожидает подтверждения'))
                        conn.commit()

                        await context.bot.send_message(
                            admin_chat_id,
                            f'Пользователь {result[0]} (ID: {user_id}) подтвердил оплату. Пожалуйста, введите "Подтвердить оплату {result[0]}".'
                        )

                        return ConversationHandler.END
                    else:
                        await update.message.reply_text('Пожалуйста, напишите "Готово", когда будете готовы сделать оплату.')
                        return CHOOSE_PAYMENT_WAITING

                async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                    text = update.message.text.split()
                    if len(text) == 4 and text[0] == "Подтвердить" and text[1] == "оплату":
                        user_name = text[2]  # Имя пользователя

                        cursor.execute('SELECT user_id FROM users WHERE name = ?', (user_name,))
                        user = cursor.fetchone()

                        if user:
                            user_id = user[0]
                            cursor.execute('UPDATE transactions SET status = ? WHERE user_id = ? AND status = ?',
                                           ('подтверждено', user_id, 'ожидает подтверждения'))
                            conn.commit()
                            await update.message.reply_text(f'Оплата пользователя {user_name} успешно подтверждена.')
                        else:
                            await update.message.reply_text('Пользователь не найден.')
                    else:
                        await update.message.reply_text('Неверная команда. Используйте "Подтвердить оплату <имя пользователя>".')

                async def show_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                    cursor.execute('SELECT * FROM transactions')
                    transactions = cursor.fetchall()

                    if transactions:
                        transaction_messages = []
                        for transaction in transactions:
                            transaction_messages.append(
                                f'ID: {transaction[0]}, Пользователь ID: {transaction[1]}, Имя: {transaction[2]}, '
                                f'Цена: {transaction[3]}, Статус: {transaction[4]}'
                            )
                        await update.message.reply_text('\n'.join(transaction_messages))
                    else:
                        await update.message.reply_text('Нет транзакций.')

                # Основная функция
                def main():
                    application = ApplicationBuilder().token(TOKEN).build()

                    # Определяем обработчики событий
                    conv_handler = ConversationHandler(
                        entry_points=[CommandHandler('start', start)],
                        states={
                            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
                            CHOOSE_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_topic)],
                            CHOOSE_PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_payment)],
                                CHOOSE_PAYMENT_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_for_payment_confirmation)],
                            },
                            fallbacks=[],
                        )

                        application.add_handler(conv_handler)
                        application.add_handler(CommandHandler('trans', show_transactions))
                        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_payment))

                        # Запускаем бота
                        application.run_polling()

                   if __name__ == "__main__":
    run()