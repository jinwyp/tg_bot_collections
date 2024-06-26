from os import environ
import re
import time

import google.generativeai as genai
from google.generativeai.types.generation_types import StopCandidateException
from telebot import TeleBot
from telebot.types import Message

from telegramify_markdown import convert
from telegramify_markdown.customize import markdown_symbol

from . import *

markdown_symbol.head_level_1 = "📌"  # If you want, Customizing the head level 1 symbol
markdown_symbol.link = "🔗"  # If you want, Customizing the link symbol

GOOGLE_GEMINI_KEY = environ.get("GOOGLE_GEMINI_KEY")

genai.configure(api_key=GOOGLE_GEMINI_KEY)
generation_config = {
    "temperature": 0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 8192,
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# Global history cache
gemini_player_dict = {}
gemini_pro_player_dict = {}


def make_new_gemini_convo(is_pro=False):
    model_name = "models/gemini-1.0-pro-latest"
    if is_pro:
        model_name = "models/gemini-1.5-pro-latest"

    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config=generation_config,
        safety_settings=safety_settings,
    )
    convo = model.start_chat()
    return convo


def gemini_handler(message: Message, bot: TeleBot) -> None:
    """Gemini : /gemini <question>"""
    m = message.text.strip()
    player = None
    # restart will lose all TODO
    if str(message.from_user.id) not in gemini_player_dict:
        player = make_new_gemini_convo()
        gemini_player_dict[str(message.from_user.id)] = player
    else:
        player = gemini_player_dict[str(message.from_user.id)]
    if m.strip() == "clear":
        bot.reply_to(
            message,
            "just clear you gemini messages history",
        )
        player.history.clear()
        return

    # show something, make it more responsible
    reply_id = bot_reply_first(message, "Gemini", bot)

    # keep the last 5, every has two ask and answer.
    if len(player.history) > 10:
        player.history = player.history[2:]

    try:
        player.send_message(m)
        gemini_reply_text = player.last.text.strip()
        # Gemini is often using ':' in **Title** which not work in Telegram Markdown
        gemini_reply_text = gemini_reply_text.replace(":**", "\:**")
        gemini_reply_text = gemini_reply_text.replace("：**", "**\: ")
    except StopCandidateException as e:
        match = re.search(r'content\s*{\s*parts\s*{\s*text:\s*"([^"]+)"', str(e))
        if match:
            gemini_reply_text = match.group(1)
            gemini_reply_text = re.sub(r"\\n", "\n", gemini_reply_text)
        else:
            print("No meaningful text was extracted from the exception.")
            bot.reply_to(
                message,
                "Google gemini encountered an error while generating an answer. Please check the log.",
            )
            return

    # By default markdown
    bot_reply_markdown(reply_id, "Gemini", gemini_reply_text, bot)


def gemini_pro_handler(message: Message, bot: TeleBot) -> None:
    """Gemini : /gemini_pro <question>"""
    m = message.text.strip()
    player = None
    # restart will lose all TODO
    if str(message.from_user.id) not in gemini_pro_player_dict:
        player = make_new_gemini_convo(is_pro=True)
        gemini_pro_player_dict[str(message.from_user.id)] = player
    else:
        player = gemini_pro_player_dict[str(message.from_user.id)]
    if m.strip() == "clear":
        bot.reply_to(
            message,
            "just clear you gemini messages history",
        )
        player.history.clear()
        return

    # show something, make it more responsible
    reply_id = bot_reply_first(message, "Geminipro", bot)

    # keep the last 5, every has two ask and answer.
    if len(player.history) > 10:
        player.history = player.history[2:]

    try:
        r = player.send_message(m, stream=True)
        s = ""
        start = time.time()
        for e in r:
            s += e.text
            print(s)
            if time.time() - start > 1.7:
                start = time.time()
                try:
                    # maybe the same message
                    if not reply_id:
                        continue
                    bot.edit_message_text(
                        message_id=reply_id.message_id,
                        chat_id=reply_id.chat.id,
                        text=convert(s),
                        parse_mode="MarkdownV2",
                    )
                except Exception as e:
                    print(str(e))
        try:
            # maybe not complete
            # maybe the same message
            bot.edit_message_text(
                message_id=reply_id.message_id,
                chat_id=reply_id.chat.id,
                text=convert(s),
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            player.history.clear()
            print(str(e))
            return
    except:
        bot.reply_to(
            message,
            "claude answer:\n" + "geminipro answer timeout",
            parse_mode="MarkdownV2",
        )
        player.history.clear()
        return


def gemini_photo_handler(message: Message, bot: TeleBot) -> None:
    s = message.caption
    reply_message = bot.reply_to(
        message,
        "Generating google gemini vision answer please wait.",
    )
    prompt = s.strip()
    # get the high quaility picture.
    max_size_photo = max(message.photo, key=lambda p: p.file_size)
    file_path = bot.get_file(max_size_photo.file_id).file_path
    downloaded_file = bot.download_file(file_path)
    with open("gemini_temp.jpg", "wb") as temp_file:
        temp_file.write(downloaded_file)

    model = genai.GenerativeModel("gemini-pro-vision")
    with open("gemini_temp.jpg", "rb") as image_file:
        image_data = image_file.read()
    contents = {
        "parts": [{"mime_type": "image/jpeg", "data": image_data}, {"text": prompt}]
    }
    try:
        response = model.generate_content(contents=contents)
        bot.reply_to(message, "Gemini vision answer:\n" + response.text)
    finally:
        bot.delete_message(reply_message.chat.id, reply_message.message_id)


def register(bot: TeleBot) -> None:
    bot.register_message_handler(gemini_handler, commands=["gemini"], pass_bot=True)
    bot.register_message_handler(gemini_handler, regexp="^gemini:", pass_bot=True)
    bot.register_message_handler(
        gemini_pro_handler, commands=["gemini_pro"], pass_bot=True
    )
    bot.register_message_handler(
        gemini_pro_handler, regexp="^gemini_pro:", pass_bot=True
    )
    bot.register_message_handler(
        gemini_photo_handler,
        content_types=["photo"],
        func=lambda m: m.caption and m.caption.startswith(("gemini:", "/gemini")),
        pass_bot=True,
    )
