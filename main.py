from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext
)
import json
import os
import re

# 🔐 Bot token and channel ID
BOT_TOKEN = "8280607987:AAEqJmkGtHwq0JNiNu24q4fMzOuRw8q7E-I"
CHANNEL_ID = -1002812881439  # AJxfiles

# 🛡️ Admin user IDs
ADMINS = ["6094777159", "6269430092"]

# 📁 Load or initialize file store
if os.path.exists("file_store.json"):
    with open("file_store.json", "r") as f:
        file_store = json.load(f)
else:
    file_store = {}

# 📜 Deleted folder log (stores: user_id, folder_name, file_data)
deleted_log = []

# 💾 Save file store to disk
def save_store():
    with open("file_store.json", "w") as f:
        json.dump(file_store, f)

# 🧼 Sanitize folder name
def sanitize_folder_name(name):
    return re.sub(r'\W+', '', name.strip())[:20]

# 🚀 /start command handler
async def start(update: Update, context: CallbackContext):
    args = context.args
    user_id = str(update.effective_user.id)

    if args:
        folder = args[0]
        user_files = file_store.get(user_id, {})
        file_data = user_files.get(folder)

        if file_data:
            await update.message.reply_document(file_data['file_id'], caption=file_data.get('caption'))
        else:
            await update.message.reply_text("❌ Folder not found.")
    else:
        await update.message.reply_text("👋 Welcome! Forward a file to store it.")

# 📤 Handle incoming files and forward to channel
async def handle_file(update: Update, context: CallbackContext):
    file = update.message.document or update.message.video or update.message.audio
    if not file:
        await update.message.reply_text("⚠️ Please forward a valid file.")
        return

    context.user_data['file_id'] = file.file_id
    context.user_data['file_caption'] = update.message.caption or update.message.text

    caption = f"📦 File from {update.effective_user.first_name}"
    if update.message.document:
        await context.bot.send_document(CHANNEL_ID, file.file_id, caption=caption)
    elif update.message.video:
        await context.bot.send_video(CHANNEL_ID, file.file_id, caption=caption)
    elif update.message.audio:
        await context.bot.send_audio(CHANNEL_ID, file.file_id, caption=caption)

    await update.message.reply_text("✅ File received.\n📂 Enter folder name to store this file:")

# 📂 Handle folder name input
async def handle_text(update: Update, context: CallbackContext):
    folder = sanitize_folder_name(update.message.text)
    file_id = context.user_data.get('file_id')
    file_caption = context.user_data.get('file_caption')
    user_id = str(update.effective_user.id)

    if len(folder) < 3:
        await update.message.reply_text("⚠️ Folder name must be at least 3 characters and alphanumeric.")
        return

    if file_id:
        if user_id not in file_store:
            file_store[user_id] = {}
        file_store[user_id][folder] = {'file_id': file_id, 'caption': file_caption}
        save_store()

        await update.message.reply_text(
            f"📦 File stored in folder '{folder}'.\n🔗 Retrieve it anytime:\n"
            f"https://t.me/{context.bot.username}?start={folder}"
        )
        context.user_data.clear()
    else:
        await update.message.reply_text("⚠️ No file to store. Please forward a file first.")

# 📋 /list command with inline buttons
async def list_folders(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)

    if user_id in ADMINS:
        if not file_store:
            await update.message.reply_text("📁 No folders stored yet.")
            return

        for uid, folders in file_store.items():
            clean_folders = [f for f in folders if len(f.strip()) >= 3 and f.isalnum()]
            if not clean_folders:
                continue

            keyboard = [
                [InlineKeyboardButton(f"📎 {folder}", callback_data=f"{uid}:{folder}")]
                for folder in clean_folders
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"👤 User {uid} folders:",
                reply_markup=reply_markup
            )
    else:
        user_folders = file_store.get(user_id)
        if not user_folders:
            await update.message.reply_text("📁 You haven’t stored any folders yet.")
            return

        clean_folders = [f for f in user_folders if len(f.strip()) >= 3 and f.isalnum()]
        keyboard = [
            [InlineKeyboardButton(f"📎 {folder}", callback_data=f"{user_id}:{folder}")]
            for folder in clean_folders
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📂 Your folders:",
            reply_markup=reply_markup
        )

# 📎 Handle button taps to retrieve files or confirm delete
async def handle_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("confirm_delete:"):
        _, uid, folder = data.split(":", 2)
        if uid in file_store and folder in file_store[uid]:
            deleted_log.append((uid, folder, file_store[uid][folder]))  # Store file data too
            file_store[uid].pop(folder)
            save_store()
            await query.edit_message_text(f"✅ Folder '{folder}' deleted for user {uid}.")
        else:
            await query.edit_message_text("❌ Folder not found or already deleted.")
    elif data == "cancel_delete":
        await query.edit_message_text("❎ Deletion cancelled.")
    else:
        user_id, folder = data.split(":", 1)
        file_data = file_store.get(user_id, {}).get(folder)
        if file_data:
            await query.message.reply_document(file_data['file_id'], caption=file_data.get('caption'))
        else:
            await query.message.reply_text("❌ File not found.")

# 🗑️ /deletefolder command (admin only)
async def delete_folder(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)

    if user_id not in ADMINS:
        await update.message.reply_text("🚫 You are not authorized to delete folders.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("⚠️ Usage: /deletefolder <user_id> <folder_name>")
        return

    target_uid, folder_name = args
    folder_name = sanitize_folder_name(folder_name)

    if target_uid not in file_store or folder_name not in file_store[target_uid]:
        await update.message.reply_text("❌ Folder not found.")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_delete:{target_uid}:{folder_name}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"⚠️ Are you sure you want to delete folder '{folder_name}' for user {target_uid}?",
        reply_markup=reply_markup
    )

# 📜 /deletedlog command (admin only)
async def show_deleted_log(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)

    if user_id not in ADMINS:
        await update.message.reply_text("🚫 You are not authorized to view the log.")
        return

    if not deleted_log:
        await update.message.reply_text("📭 No folders have been deleted yet.")
        return

    log_text = "\n".join([f"👤 {uid} ➡️ 🗑️ {folder}" for uid, folder, _ in deleted_log])
    await update.message.reply_text(f"📜 Deleted Folder Log:\n{log_text}")

# 🔄 /restorefolder command (admin only)
async def restore_folder(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)

    if user_id not in ADMINS:
        await update.message.reply_text("🚫 You are not authorized to restore folders.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("⚠️ Usage: /restorefolder <user_id> <folder_name>")
        return

    target_uid, folder_name = args
    folder_name = sanitize_folder_name(folder_name)

    for i, (uid, folder, file_data) in enumerate(deleted_log):
        if uid == target_uid and folder == folder_name:
            if uid not in file_store:
                file_store[uid] = {}
            file_store[uid][folder] = file_data
            save_store()
            deleted_log.pop(i)
            await update.message.reply_text(f"✅ Folder '{folder}' restored for user {uid}.")
            return

    await update.message.reply_text("❌ No matching deleted folder found.")

# 🌐 Flask web server to keep Replit alive
app_web = Flask('')

@app_web.route('/')
def home():
    return "the owner of this web site :- nikhil THE WEBSITE project is in work and checking bugs , website will avileble soon"

@app_web.route('/ping')
def ping():
    return '''<!DOCTYPE html>
<html>
<head>
  <title>Book Card</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background-color: #f5f5f5;
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100vh;
    }

    .book-card {
      width: 250px;
      background: white;
      border-radius: 8px;
      box-shadow: 0 4px 8px rgba(0,0,0,0.1);
      overflow: hidden;
      text-align: center;
    }

    .book-card img {
      width: 100%;
      height: auto;
      object-fit: contain;
      background-color: #fff;
    }

    .book-card h3 {
      margin: 10px 0 5px;
      font-size: 18px;
    }

    .book-card p {
      font-size: 14px;
      color: #555;
    }

    .book-card a {
      display: inline-block;
      margin: 10px 0 15px;
      padding: 8px 15px;
      background: #28a745;
      color: white;
      text-decoration: none;
      border-radius: 5px;
    }

    .book-card a:hover {
      background: #218838;
    }
  </style>
</head>
<body>

  <div class="book-card">
    <img src="https://covers.openlibrary.org/b/id/14738401-L.jpg" alt="A Tale of Two Cities">
    <a href="https://drive.google.com/file/d/1Mn8-fUAtN93-D4Jrd4oKUGgzFBVWeOLe/view?usp=drivesdk " target="_blank">Read Book</a>
            
    <h3>A Tale of Two Cities</h3>
    <p>By Charles Dickens</p>

  </div>

</body>
</html>''', 200

def run():
    app_web.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 🟢 Main function to run bot
def main():
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_folders))
    app.add_handler(CommandHandler("deletefolder", delete_folder))
    app.add_handler(CommandHandler("deletedlog", show_deleted_log))
    app.add_handler(CommandHandler("restorefolder", restore_folder))  # NEW
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO | filters.AUDIO, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_button))

    app.run_polling()

# 🔁 Run main if script is executed directly
if __name__ == "__main__":
    main()
