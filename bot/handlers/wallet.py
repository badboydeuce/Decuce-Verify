"""
Wallet handlers for DeuceVerify bot
Handles balance checking, funding, and transaction history
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
import logging

from database.db import SessionLocal
from database.crud import (
    get_user_by_telegram_id,
    update_user_balance,
    create_transaction,
    get_user_transactions,
    get_or_create_user
)
from config import settings

logger = logging.getLogger(__name__)
router = Router()

# ============ FSM STATES ============

class WalletStates(StatesGroup):
    """Wallet FSM states"""
    waiting_for_funding_amount = State()
    verifying_payment = State()

# ============ HELPER FUNCTIONS ============

def format_amount(amount: float) -> str:
    """Format amount with currency"""
    return f"₦{amount:,.2f}"

def get_wallet_keyboard() -> InlineKeyboardMarkup:
    """Get wallet menu keyboard"""
    from bot.keyboards.inline_keyboards import get_wallet_keyboard
    return get_wallet_keyboard()

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Get back button keyboard"""
    from bot.keyboards.inline_keyboards import get_back_keyboard
    return get_back_keyboard("back_to_main")

def get_transaction_history_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Get transaction history pagination keyboard"""
    builder = []
    
    # Navigation buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Previous", callback_data=f"tx_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"tx_page_{page+1}"))
    
    # Back button
    back_button = InlineKeyboardButton(text="🔙 Back to Wallet", callback_data="wallet_menu")
    
    # Build keyboard rows
    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([back_button])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============ COMMAND HANDLERS ============

@router.message(F.text == "💰 Wallet")
async def wallet_menu(message: Message, state: FSMContext):
    """Handle Wallet button click"""
    await state.clear()
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            user = get_or_create_user(db, message.from_user.id, message.from_user.username)
        
        balance_text = (
            f"💰 <b>Your Wallet</b>\n\n"
            f"┌──────────────────┐\n"
            f"│  Balance: {format_amount(user.balance)}\n"
            f"└──────────────────┘\n\n"
            f"<b>Quick Actions:</b>\n"
            f"• Fund your wallet to start buying numbers\n"
            f"• Minimum funding: {format_amount(settings.minimum_funding_ngn)}\n"
            f"• Payments are processed instantly via Paystack\n\n"
            f"<i>Select an option below:</i>"
        )
        
        await message.answer(
            balance_text,
            reply_markup=get_wallet_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in wallet_menu: {e}")
        await message.answer("❌ An error occurred. Please try again later.")
    finally:
        db.close()

@router.message(F.text == "💳 Fund Wallet")
async def fund_wallet_prompt(message: Message, state: FSMContext):
    """Handle Fund Wallet button - prompt for amount"""
    await state.set_state(WalletStates.waiting_for_funding_amount)
    
    await message.answer(
        f"💳 <b>Fund Wallet</b>\n\n"
        f"Enter the amount you want to fund (NGN):\n\n"
        f"• Minimum: {format_amount(settings.minimum_funding_ngn)}\n"
        f"• No maximum limit\n"
        f"• 1.5% service fee applies to purchases, not deposits\n\n"
        f"<i>Send the amount as a number (e.g., 5000)</i>\n"
        f"Or click /cancel to go back.",
        parse_mode="HTML",
        reply_markup=get_back_keyboard()
    )

@router.message(WalletStates.waiting_for_funding_amount)
async def process_funding_amount(message: Message, state: FSMContext):
    """Process the funding amount input"""
    try:
        # Parse amount
        amount_text = message.text.strip()
        amount = float(amount_text)
        
        # Validate minimum
        if amount < settings.minimum_funding_ngn:
            await message.answer(
                f"❌ <b>Invalid Amount</b>\n\n"
                f"Minimum funding amount is {format_amount(settings.minimum_funding_ngn)}.\n"
                f"Please enter a higher amount.\n\n"
                f"Send /cancel to abort.",
                parse_mode="HTML"
            )
            return
        
        # Validate positive number
        if amount <= 0:
            await message.answer(
                f"❌ <b>Invalid Amount</b>\n\n"
                f"Amount must be greater than 0.\n\n"
                f"Send /cancel to abort.",
                parse_mode="HTML"
            )
            return
        
        # Store amount in state
        await state.update_data(funding_amount=amount)
        
        # Get user email (prompt if not available)
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, message.from_user.id)
            email = f"user_{message.from_user.id}@deuceverify.com"
            
            # Initialize Paystack payment
            api_url = f"http://localhost:{settings.flask_port}/api/wallet/fund"
            
            # Show loading message
            loading_msg = await message.answer(
                "⏳ <b>Initializing payment...</b>\n\n"
                "Please wait while we create your payment link.",
                parse_mode="HTML"
            )
            
            # Make API request to initialize payment
            response = requests.post(
                api_url,
                json={
                    "telegram_id": message.from_user.id,
                    "amount": amount,
                    "email": email
                },
                timeout=30
            )
            
            await loading_msg.delete()
            
            if response.status_code == 200:
                data = response.json()
                auth_url = data.get("authorization_url")
                reference = data.get("reference")
                
                if auth_url:
                    # Store reference in state
                    await state.update_data(payment_reference=reference)
                    
                    payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💳 Pay Now", url=auth_url)],
                        [InlineKeyboardButton(text="✅ I've Completed Payment", callback_data=f"verify_payment_{reference}")],
                        [InlineKeyboardButton(text="❌ Cancel", callback_data="wallet_menu")]
                    ])
                    
                    await message.answer(
                        f"💳 <b>Payment Initiated</b>\n\n"
                        f"Amount: {format_amount(amount)}\n"
                        f"Reference: <code>{reference}</code>\n\n"
                        f"<b>Instructions:</b>\n"
                        f"1️⃣ Click the 'Pay Now' button below\n"
                        f"2️⃣ Complete payment on Paystack\n"
                        f"3️⃣ Click 'Verify Payment' after completion\n\n"
                        f"<i>Your wallet will be credited automatically after successful payment.</i>",
                        parse_mode="HTML",
                        reply_markup=payment_keyboard
                    )
                else:
                    await message.answer(
                        "❌ <b>Payment Initialization Failed</b>\n\n"
                        "Unable to create payment link. Please try again later.\n\n"
                        "If the problem persists, contact support.",
                        parse_mode="HTML",
                        reply_markup=get_back_keyboard()
                    )
            else:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", "Unknown error")
                await message.answer(
                    f"❌ <b>Payment Initiation Failed</b>\n\n"
                    f"Error: {error_msg}\n\n"
                    f"Please try again later.",
                    parse_mode="HTML",
                    reply_markup=get_back_keyboard()
                )
        finally:
            db.close()
            
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Amount</b>\n\n"
            "Please enter a valid number (e.g., 5000).\n\n"
            "Send /cancel to abort.",
            parse_mode="HTML"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Payment API error: {e}")
        await message.answer(
            "❌ <b>Service Error</b>\n\n"
            "Unable to connect to payment service. Please try again later.\n\n"
            "Send /cancel to abort.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error processing funding: {e}")
        await message.answer(
            "❌ <b>Unexpected Error</b>\n\n"
            "An error occurred. Please try again later.",
            parse_mode="HTML",
            reply_markup=get_back_keyboard()
        )

@router.message(F.text == "📜 Transaction History")
async def transaction_history(message: Message, state: FSMContext):
    """Handle Transaction History button"""
    await state.clear()
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            await message.answer("Please use /start to register first.")
            return
        
        # Get transactions with pagination (page 1, 10 per page)
        transactions = get_user_transactions(db, user.id, limit=10, offset=0)
        total_count = db.query(Transaction).filter(Transaction.user_id == user.id).count()
        
        if not transactions:
            await message.answer(
                "📜 <b>Transaction History</b>\n\n"
                "No transactions found.\n\n"
                "Use 'Fund Wallet' to make your first deposit!",
                parse_mode="HTML",
                reply_markup=get_back_keyboard()
            )
            return
        
        # Build transaction list
        tx_list = []
        for tx in transactions[:10]:
            emoji = "➕" if tx.type.value == "credit" else "➖"
            status_emoji = "✅" if tx.status == "completed" else "⏳"
            tx_list.append(
                f"{emoji} {status_emoji} {format_amount(tx.amount)} - {tx.type.value.upper()}\n"
                f"   └─ {tx.description or 'N/A'} | {tx.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
        
        total_pages = (total_count + 9) // 10  # Ceiling division
        
        history_text = (
            f"📜 <b>Transaction History</b>\n\n"
            f"{chr(10).join(tx_list)}\n\n"
            f"<i>Page 1 of {total_pages}</i>"
        )
        
        await message.answer(
            history_text,
            parse_mode="HTML",
            reply_markup=get_transaction_history_keyboard(1, total_pages)
        )
        
    except Exception as e:
        logger.error(f"Error in transaction_history: {e}")
        await message.answer("❌ An error occurred. Please try again later.")
    finally:
        db.close()

@router.callback_query(lambda c: c.data and c.data.startswith("tx_page_"))
async def transaction_history_page(callback: CallbackQuery):
    """Handle transaction history pagination"""
    page = int(callback.data.split("_")[2])
    limit = 10
    offset = (page - 1) * limit
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, callback.from_user.id)
        if not user:
            await callback.answer("User not found", show_alert=True)
            return
        
        from database.models import Transaction
        transactions = get_user_transactions(db, user.id, limit=limit, offset=offset)
        total_count = db.query(Transaction).filter(Transaction.user_id == user.id).count()
        total_pages = (total_count + limit - 1) // limit
        
        if not transactions:
            await callback.answer("No more transactions", show_alert=True)
            return
        
        # Build transaction list
        tx_list = []
        for tx in transactions:
            emoji = "➕" if tx.type.value == "credit" else "➖"
            status_emoji = "✅" if tx.status == "completed" else "⏳"
            tx_list.append(
                f"{emoji} {status_emoji} {format_amount(tx.amount)} - {tx.type.value.upper()}\n"
                f"   └─ {tx.description or 'N/A'} | {tx.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
        
        history_text = (
            f"📜 <b>Transaction History</b>\n\n"
            f"{chr(10).join(tx_list)}\n\n"
            f"<i>Page {page} of {total_pages}</i>"
        )
        
        await callback.message.edit_text(
            history_text,
            parse_mode="HTML",
            reply_markup=get_transaction_history_keyboard(page, total_pages)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in transaction history page: {e}")
        await callback.answer("Error loading page", show_alert=True)
    finally:
        db.close()

@router.callback_query(lambda c: c.data and c.data.startswith("verify_payment_"))
async def verify_payment(callback: CallbackQuery, state: FSMContext):
    """Verify payment after user clicks verify button"""
    reference = callback.data.split("_")[2]
    
    # Show loading
    await callback.message.edit_text(
        "⏳ <b>Verifying Payment...</b>\n\n"
        "Please wait while we confirm your transaction.\n"
        "This may take a few seconds.",
        parse_mode="HTML"
    )
    
    # Call API to verify payment
    api_url = f"http://localhost:{settings.flask_port}/api/payment/verify/{reference}"
    
    try:
        # In a real implementation, you would call Paystack verification endpoint
        # For now, we'll simulate by checking webhook status
        
        # Since webhook automatically processes, we just check if balance increased
        await asyncio.sleep(3)  # Wait for webhook to process
        
        db = SessionLocal()
        try:
            user = get_user_by_telegram_id(db, callback.from_user.id)
            if user:
                # Check if any new transaction with this reference exists
                from database.models import Transaction
                transaction = db.query(Transaction).filter(
                    Transaction.reference == reference,
                    Transaction.user_id == user.id
                ).first()
                
                if transaction and transaction.status == "completed":
                    await callback.message.edit_text(
                        f"✅ <b>Payment Successful!</b>\n\n"
                        f"Your wallet has been credited with {format_amount(transaction.amount)}.\n\n"
                        f"New balance: {format_amount(user.balance)}\n\n"
                        f"You can now use your balance to purchase virtual numbers.",
                        parse_mode="HTML",
                        reply_markup=get_wallet_keyboard()
                    )
                else:
                    await callback.message.edit_text(
                        f"⏳ <b>Payment Pending</b>\n\n"
                        f"Your payment is still being processed.\n\n"
                        f"Reference: <code>{reference}</code>\n\n"
                        f"The funds will be credited automatically once confirmed.\n"
                        f"This usually takes 1-2 minutes.\n\n"
                        f"You can check your balance again in a few moments.",
                        parse_mode="HTML",
                        reply_markup=get_wallet_keyboard()
                    )
            else:
                await callback.message.edit_text(
                    "❌ <b>Verification Failed</b>\n\n"
                    "User not found. Please contact support.",
                    parse_mode="HTML",
                    reply_markup=get_back_keyboard()
                )
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        await callback.message.edit_text(
            "❌ <b>Verification Error</b>\n\n"
            "Unable to verify payment at this time.\n\n"
            f"Reference: <code>{reference}</code>\n\n"
            "If funds were deducted, they will be credited automatically.\n"
            "Please check your balance in a few minutes or contact support.",
            parse_mode="HTML",
            reply_markup=get_wallet_keyboard()
        )
    
    await callback.answer()

@router.callback_query(F.data == "wallet_menu")
async def wallet_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Handle wallet menu callback"""
    await state.clear()
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, callback.from_user.id)
        if user:
            balance_text = (
                f"💰 <b>Your Wallet</b>\n\n"
                f"┌──────────────────┐\n"
                f"│  Balance: {format_amount(user.balance)}\n"
                f"└──────────────────┘\n\n"
                f"<b>Quick Actions:</b>\n"
                f"• Fund your wallet to start buying numbers\n"
                f"• Minimum funding: {format_amount(settings.minimum_funding_ngn)}\n\n"
                f"<i>Select an option below:</i>"
            )
            
            await callback.message.edit_text(
                balance_text,
                parse_mode="HTML",
                reply_markup=get_wallet_keyboard()
            )
        await callback.answer()
    finally:
        db.close()

@router.message(F.text == "🔙 Back to Wallet")
async def back_to_wallet(message: Message, state: FSMContext):
    """Handle back to wallet"""
    await wallet_menu(message, state)

# Import required models
from database.models import Transaction
import asyncio
