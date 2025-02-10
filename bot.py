import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from tgtg import TgtgClient
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from models import Session, User, NotifiedBag, init_db

# --- Logging Configuration ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv()

# --- Global Configuration ---
LATITUDE = 48.126
LONGITUDE = -1.723
RADIUS = 10
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

def get_client_for_user(user: User) -> TgtgClient:
    """Create TGTG client from user credentials"""
    return TgtgClient(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        cookie=user.cookie
    )

def format_pickup_interval(start: str, end: str) -> str:
    """Format pickup interval in a clean way"""
    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

    date_format = "%d/%m/%Y"
    time_format = "%H:%M"

    if start_dt.date() == end_dt.date():
        # Same day
        return f"{start_dt.strftime(date_format)} {start_dt.strftime(time_format)}-{end_dt.strftime(time_format)}"
    else:
        # Different days
        return f"{start_dt.strftime(date_format)} {start_dt.strftime(time_format)} - {end_dt.strftime(date_format)} {end_dt.strftime(time_format)}"

async def start(update: Update, context: CallbackContext):
    """Start command handler with available commands info"""
    assert update.message is not None
    message = (
        "Ciao! Ecco i comandi disponibili:\n\n"
        "/start - Mostra questo messaggio\n"
        "/status - Controlla il tuo stato attuale\n"
        "/remove - Rimuovi la tua email e smetti di ricevere notifiche\n\n"
        "Per iniziare, inviami la tua email!"
    )
    await update.message.reply_text(message)

async def status(update: Update, context: CallbackContext):
    """Check current user status"""
    assert update.message is not None
    chat_id = update.message.chat_id
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        if user:
            message = f"📧 Email registrata: {user.email}\n"
            message += f"🔔 Al momento hai {len(user.notified_bags)} surprise bag preferite disponibili"
        else:
            message = "❌ Nessuna email registrata. Inviami la tua email per iniziare!"
    await update.message.reply_text(message)

async def remove(update: Update, context: CallbackContext):
    """Remove user data and stop notifications"""
    assert update.message is not None
    chat_id = update.message.chat_id
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        if user:
            session.delete(user)
            session.commit()
            await update.message.reply_text("✅ La tua email è stata rimossa. Non riceverai più notifiche.")
        else:
            await update.message.reply_text("❌ Nessuna email registrata.")

async def handle_email(update: Update, context: CallbackContext):
    assert update.message is not None
    assert update.message.text is not None
    email = update.message.text.strip().lower()
    chat_id = update.message.chat_id

    with Session() as session:
        # Check if already registered
        if session.query(User).filter_by(chat_id=chat_id).first():
            await update.message.reply_text("⚠️ Sei già registrato! Usa /remove per cambiare email.")
            return

        # Check if email exists in database
        existing_user = session.query(User).filter_by(email=email).first()
        if existing_user:
            try:
                client = get_client_for_user(existing_user)
                new_user = User(
                    chat_id=chat_id,
                    email=email,
                    access_token=existing_user.access_token,
                    refresh_token=existing_user.refresh_token,
                    cookie=existing_user.cookie
                )
                session.add(new_user)
                session.commit()
                await update.message.reply_text(
                    f"✅ Bentornato! Registrato con successo per {email}!"
                )
                return
            except Exception:
                pass

    # Start login process
    try:
        await update.message.reply_text(
            "🔄 Ti sta per arrivare una email da TooGoodToGo!\n"
            "Clicca sul link nella email per completare la registrazione.\n"
            "⚠️⚠️ Se sei da mobile apri il link nel browser (tenendo premuto sul link, Condividi > browser). ⚠️⚠️\nAprire il link con l'app di TooGoodToGo non funzionerà."
        )

        client = TgtgClient(email=email)

        # Attendi che l'utente clicchi il link
        for _ in range(3):
            try:
                creds = client.get_credentials()
                if "access_token" in creds:
                    # User has clicked the link
                    with Session() as session:
                        new_user = User(
                            chat_id=chat_id,
                            email=email,
                            access_token=creds["access_token"],
                            refresh_token=creds["refresh_token"],
                            cookie=creds["cookie"]
                        )
                        session.add(new_user)
                        session.commit()

                    await update.message.reply_text(
                        f"✅ Registrato con successo per {email}!\n"
                        f"Riceverai notifiche quando i tuoi prodotti preferiti saranno disponibili."
                    )
                    return
            except Exception as e:
                logger.error(f"Error checking credentials: {e}")
                await asyncio.sleep(10)  # attendi 10 secondi tra i tentativi
                continue

        # Se arriviamo qui, il timeout è scaduto
        await update.message.reply_text(
            "⏰ Tempo scaduto!\n"
            "Non hai cliccato il link in tempo. Riprova inviando nuovamente la tua email."
        )

    except Exception as e:
        logger.error(f"Error starting login for {email}: {e}")
        await update.message.reply_text("❌ Si è verificato un errore durante il login. Riprova più tardi.")

async def check_favorites(context: CallbackContext):
    with Session() as session:
        users = session.query(User).all()
        for user in users:
            try:
                client = get_client_for_user(user)
                favorites = client.get_favorites(
                    latitude=LATITUDE,
                    longitude=LONGITUDE,
                    radius=RADIUS,
                )
            except Exception as e:
                logger.error(f"Errore per {user.email}: {e}")
                continue

            # Get current favorite item IDs
            favorite_ids = {str(item["item"]["item_id"]) for item in favorites} if favorites else set()

            # Remove notifications for items no longer in favorites
            for notified_bag in user.notified_bags:
                if notified_bag.item_id not in favorite_ids:
                    session.delete(notified_bag)

            notified_ids = {bag.item_id for bag in user.notified_bags}

            for item in favorites:
                try:
                    item_id = str(item["item"]["item_id"])
                    items_available = item["items_available"]

                    if items_available == 0 and item_id in notified_ids:
                        session.query(NotifiedBag).filter_by(
                            chat_id=user.chat_id,
                            item_id=item_id
                        ).delete()
                        continue

                    if items_available > 0 and item_id not in notified_ids:
                        store_name = item["store"]["store_name"]
                        display_name = item["display_name"]
                        description = item["item"]["description"].split("\n")[0]
                        pickup_interval = item["pickup_interval"]
                        pickup_time: str = format_pickup_interval(
                            pickup_interval["start"],
                            pickup_interval["end"]
                        )
                        price = item["item"]["item_price"]["minor_units"] / 100
                        value = item["item"]["item_value"]["minor_units"] / 100
                        image_url = item["item"]["cover_picture"]["current_url"]

                        message = (
                            f"🎉 Nuova Magic Bag disponibile!\n\n"
                            f"🏪 <b>{store_name}</b>\n"
                            f"📦 {display_name}\n"
                            f"📝 {description}\n\n"
                            f"💰 Prezzo: {price:.2f}€\n"
                            f"💎 Valore: {value:.2f}€\n"
                            f"📦 Disponibili: {items_available}\n"
                            f"⏰ Ritiro: {pickup_time}\n\n"
                            f"⚡️ Affrettati, potrebbero esaurirsi velocemente!"
                        )

                        try:
                            await context.bot.send_photo(
                                chat_id=user.chat_id,
                                photo=image_url,
                                caption=message,
                                parse_mode='HTML'
                            )
                        except Exception:
                            await context.bot.send_message(
                                chat_id=user.chat_id,
                                text=message,
                                parse_mode='HTML'
                            )

                        session.add(NotifiedBag(chat_id=user.chat_id, item_id=item_id))
                except KeyError as e:
                    logger.error(f"Chiave mancante nell'item: {e}")
                    continue

            session.commit()

def main():
    # Initialize database
    init_db()

    # Initialize the application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email))

    # Setup job queue
    assert application.job_queue is not None
    application.job_queue.run_repeating(check_favorites, interval=60, first=5)

    logger.info("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
