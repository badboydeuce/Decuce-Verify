from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
import os
import json

router = Router()

class FundWalletStates(StatesGroup):
    waiting_for_custom_amount = State()

@router.callback_query(F.data == "menu_wallet")
async def menu_wallet(callback: CallbackQuery, db_manager):
    """Show wallet menu"""
    session = db_manager.get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Fund Wallet (Paystack NGN)", callback_data="fund_paystack")],
            [InlineKeyboardButton(text="₿ Fund Wallet (Crypto USDT)", callback_data="fund_crypto")],
            [InlineKeyboardButton(text="📊 Transaction History", callback_data="txn_history")],
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
        ])
        
        await callback.message.edit_text(
            f"💰 <b>Your Wallet</b>\n\n"
            f"💰 Balance: <b>${user.balance:.2f} USD</b>\n"
            f"📊 Total spent: ${user.total_spent:.2f}\n"
            f"🔄 Total orders: {user.total_orders}\n\n"
            f"<i>Minimum deposit: ₦500 ($0.33) | Maximum: ₦500,000 ($333)</i>\n\n"
            f"Select an option below:",
            reply_markup=keyboard
        )
    finally:
        session.close()

@router.callback_query(F.data == "fund_paystack")
async def fund_paystack(callback: CallbackQuery):
    """Show Paystack funding options"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₦1,000 (~$0.67)", callback_data="paystack_1000"),
         InlineKeyboardButton(text="₦2,000 (~$1.33)", callback_data="paystack_2000")],
        [InlineKeyboardButton(text="₦5,000 (~$3.33)", callback_data="paystack_5000"),
         InlineKeyboardButton(text="₦10,000 (~$6.67)", callback_data="paystack_10000")],
        [InlineKeyboardButton(text="₦20,000 (~$13.33)", callback_data="paystack_20000"),
         InlineKeyboardButton(text="₦50,000 (~$33.33)", callback_data="paystack_50000")],
        [InlineKeyboardButton(text="✏️ Custom Amount", callback_data="paystack_custom")],
        [InlineKeyboardButton(text="🔙 Back to Wallet", callback_data="menu_wallet")]
    ])
    
    await callback.message.edit_text(
        "💳 <b>Fund Wallet with Paystack</b>\n\n"
        "Select an amount in NGN (Nigerian Naira):\n\n"
        "✅ Instant crediting\n"
        "✅ Card, Bank Transfer, USSD\n"
        "✅ Secure payment\n\n"
        "Your wallet will be credited automatically after payment.",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("paystack_"))
async def process_paystack_payment(callback: CallbackQuery, state: FSMContext, db_manager):
    """Process Paystack payment"""
    amount_str = callback.data.split("_")[1]
    
    if amount_str == "custom":
        await callback.message.answer(
            "💰 <b>Enter Custom Amount</b>\n\n"
            "Please enter the amount in NGN (₦):\n"
            "Minimum: ₦500\n"
            "Maximum: ₦500,000\n\n"
            "Send the amount as a number (e.g., 2500)\n\n"
            "Type /cancel to cancel.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="fund_paystack")]
            ])
        )
        await state.set_state(FundWalletStates.waiting_for_custom_amount)
        return
    
    amount_ngn = int(amount_str)
    await initiate_payment(callback, amount_ngn, db_manager)

@router.message(FundWalletStates.waiting_for_custom_amount)
async def process_custom_amount(message: Message, state: FSMContext, db_manager):
    """Process custom amount"""
    try:
        amount_ngn = int(message.text.strip())
        
        if amount_ngn < 500:
            await message.answer("❌ Minimum amount is ₦500. Please try again.")
            return
        if amount_ngn > 500000:
            await message.answer("❌ Maximum amount is ₦500,000. Please try again.")
            return
        
        # Create a callback query-like object
        class FakeCallback:
            def __init__(self, message, user_id):
                self.message = message
                self.from_user = type('obj', (object,), {'id': user_id})()
                self.answer = lambda x: None
        
        fake_callback = FakeCallback(message, message.from_user.id)
        await initiate_payment(fake_callback, amount_ngn, db_manager)
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Please enter a valid number.")

async def initiate_payment(callback, amount_ngn, db_manager):
    """Initialize payment with Paystack"""
    await callback.answer("⏳ Initializing payment...")
    
    # Get user email (use Telegram ID as fallback)
    user_email = f"user_{callback.from_user.id}@deuceverify.com"
    
    # Call our API to create payment
    api_url = os.getenv('API_URL', 'http://localhost:5000')
    
    try:
        response = requests.post(
            f"{api_url}/api/create-payment",
            json={
                "telegram_id": callback.from_user.id,
                "email": user_email,
                "amount": amount_ngn
            },
            timeout=30
        )
        
        result = response.json()
        
        if result.get('success'):
            payment_url = result['authorization_url']
            reference = result['reference']
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Click to Pay Now", url=payment_url)],
                [InlineKeyboardButton(text="✅ I've Completed Payment", callback_data=f"check_payment_{reference}")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="fund_paystack")]
            ])
            
            await callback.message.edit_text(
                f"💳 <b>Payment Initiated</b>\n\n"
                f"Amount: <b>₦{amount_ngn:,}</b>\n"
                f"Reference: <code>{reference}</code>\n\n"
                f"📌 <b>Instructions:</b>\n"
                f"1. Click the payment button below\n"
                f"2. Complete payment on Paystack page\n"
                f"3. Click 'I've Completed Payment' after paying\n\n"
                f"⚠️ Your wallet will be credited automatically within 1-2 minutes.",
                reply_markup=keyboard
            )
        else:
            error_msg = result.get('error', 'Payment initialization failed')
            await callback.message.edit_text(
                f"❌ Payment failed: {error_msg}\n\nPlease try again later.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Try Again", callback_data="fund_paystack")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="menu_wallet")]
                ])
            )
            
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Error: {str(e)}\n\nPlease try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data="fund_paystack")]
            ])
        )

@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_status(callback: CallbackQuery, db_manager):
    """Manually check payment status"""
    reference = callback.data.split("_")[2]
    
    # Verify with Paystack
    headers = {
        "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers
        )
        
        result = response.json()
        
        if result.get('status') and result['data']['status'] == 'success':
            amount = result['data']['amount'] / 100
            usd_amount = amount / 1500
            
            # Update database directly
            session = db_manager.get_session()
            try:
                transaction = session.query(Transaction).filter_by(payment_reference=reference).first()
                if transaction and transaction.status.value == 'pending':
                    transaction.status = TransactionStatus.COMPLETED
                    transaction.completed_at = datetime.utcnow()
                    
                    user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
                    if user:
                        user.balance += usd_amount
                        session.commit()
                        
                        await callback.message.edit_text(
                            f"✅ <b>Payment Successful!</b>\n\n"
                            f"Amount: ₦{amount:,.2f}\n"
                            f"Added to wallet: <b>${usd_amount:.2f}</b>\n\n"
                            f"💰 New balance: <b>${user.balance:.2f}</b>\n\n"
                            f"You can now rent numbers!",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="📱 Buy Number", callback_data="menu_buy")],
                                [InlineKeyboardButton(text="💰 Check Balance", callback_data="menu_wallet")]
                            ])
                        )
                    else:
                        await callback.message.edit_text("❌ User not found.")
                else:
                    await callback.message.edit_text(
                        "ℹ️ Payment already processed or transaction not found.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="💰 Check Balance", callback_data="menu_wallet")]
                        ])
                    )
            finally:
                session.close()
        else:
            await callback.message.edit_text(
                "⏳ Payment not confirmed yet.\n\n"
                "Please complete the payment on Paystack and try again.\n"
                "If you've paid, it may take 1-2 minutes to process.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Check Again", callback_data=f"check_payment_{reference}")],
                    [InlineKeyboardButton(text="💰 Back to Wallet", callback_data="menu_wallet")]
                ])
            )
            
    except Exception as e:
        await callback.message.edit_text(f"❌ Error checking payment: {str(e)}")

@router.callback_query(F.data == "txn_history")
async def transaction_history(callback: CallbackQuery, db_manager):
    """Show transaction history"""
    session = db_manager.get_session()
    try:
        transactions = session.query(Transaction).filter_by(
            user_id=callback.from_user.id
        ).order_by(Transaction.created_at.desc()).limit(20).all()
        
        if not transactions:
            await callback.message.edit_text(
                "📊 <b>Transaction History</b>\n\n"
                "No transactions yet.\n\n"
                "Fund your wallet to get started!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Fund Wallet", callback_data="fund_paystack")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="menu_wallet")]
                ])
            )
            return
        
        history_text = "📊 <b>Transaction History</b>\n\n"
        for tx in transactions[:10]:  # Show last 10
            emoji = "➕" if tx.type == TransactionType.CREDIT else "➖"
            status_emoji = "✅" if tx.status == TransactionStatus.COMPLETED else "⏳"
            history_text += f"{emoji} {status_emoji} <b>${tx.amount:.2f}</b> - {tx.description[:30]}\n"
            history_text += f"   <i>{tx.created_at.strftime('%Y-%m-%d %H:%M')}</i>\n\n"
        
        history_text += f"\n<i>Showing last {min(10, len(transactions))} of {len(transactions)} transactions</i>"
        
        await callback.message.edit_text(
            history_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 Fund Wallet Again", callback_data="fund_paystack")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu_wallet")]
            ])
        )
    finally:
        session.close()
