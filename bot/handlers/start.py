# /start handler
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from models.database import User
from datetime import datetime

router = Router()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Buy Number", callback_data="menu_buy"),
         InlineKeyboardButton(text="💰 Wallet", callback_data="menu_wallet")],
        [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders"),
         InlineKeyboardButton(text="👤 Profile", callback_data="menu_profile")],
        [InlineKeyboardButton(text="❓ Support", callback_data="menu_support")]
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, db_manager):
    session = db_manager.get_session()
    try:
        user = session.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                created_at=datetime.utcnow()
            )
            session.add(user)
            session.commit()
            await message.answer("🎉 Welcome to DeuceVerify!\n\nYour virtual number SMS verification platform.\n\nUse the menu below to get started.", reply_markup=main_menu())
        else:
            await message.answer(f"👋 Welcome back, {user.first_name}!\n\n💰 Balance: ${user.balance:.2f}\n\nWhat would you like to do?", reply_markup=main_menu())
    finally:
        session.close()

@router.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery, db_manager):
    session = db_manager.get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        await callback.message.edit_text(
            f"👤 <b>Your Profile</b>\n\n"
            f"Name: {user.first_name}\n"
            f"Balance: <b>${user.balance:.2f}</b>\n"
            f"Total orders: {user.total_orders}\n"
            f"Total spent: ${user.total_spent:.2f}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
            ])
        )
    finally:
        session.close()

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text("Main Menu:", reply_markup=main_menu())
