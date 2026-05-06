# Wallet handler
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import requests
import os

router = Router()

@router.callback_query(F.data == "menu_wallet")
async def menu_wallet(callback: CallbackQuery, db_manager):
    session = db_manager.get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        await callback.message.edit_text(
            f"💰 <b>Your Wallet</b>\n\nBalance: <b>${user.balance:.2f}</b>\n\nSelect an option:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Fund Wallet (Paystack)", callback_data="fund_paystack")],
                [InlineKeyboardButton(text="📊 Transaction History", callback_data="txn_history")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
            ])
        )
    finally:
        session.close()

@router.callback_query(F.data == "fund_paystack")
async def fund_paystack(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₦1,000", callback_data="amount_1000"),
         InlineKeyboardButton(text="₦2,000", callback_data="amount_2000")],
        [InlineKeyboardButton(text="₦5,000", callback_data="amount_5000"),
         InlineKeyboardButton(text="₦10,000", callback_data="amount_10000")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_wallet")]
    ])
    await callback.message.edit_text("Select amount to fund:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("amount_"))
async def process_funding(callback: CallbackQuery, db_manager):
    amount = int(callback.data.split("_")[1])
    
    # Initialize Paystack transaction
    headers = {"Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}", "Content-Type": "application/json"}
    payload = {
        "email": f"user_{callback.from_user.id}@deuceverify.com",
        "amount": amount * 100,
        "currency": "NGN",
        "metadata": {"telegram_id": callback.from_user.id}
    }
    
    response = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    data = response.json()
    
    if data['status']:
        await callback.message.edit_text(
            f"💰 Payment initiated!\n\nAmount: ₦{amount}\n\nClick the button below to pay:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Pay Now", url=data['data']['authorization_url'])],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu_wallet")]
            ])
        )
