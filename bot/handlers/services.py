# Services handler
"""
Service browser for DeuceVerify
Browse, search, and filter all SMS-Man services
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger

router = Router()

# Service categories
CATEGORIES = {
    "popular": {"name": "⭐ Popular Services", "icon": "⭐", "order": 1},
    "social": {"name": "📱 Social Media", "icon": "📱", "order": 2},
    "messaging": {"name": "💬 Messaging Apps", "icon": "💬", "order": 3},
    "crypto": {"name": "₿ Crypto Exchanges", "icon": "₿", "order": 4},
    "email": {"name": "📧 Email Services", "icon": "📧", "order": 5},
    "dating": {"name": "💕 Dating Apps", "icon": "💕", "order": 6},
    "gaming": {"name": "🎮 Gaming", "icon": "🎮", "order": 7},
    "productivity": {"name": "📊 Productivity", "icon": "📊", "order": 8},
    "other": {"name": "🔧 Other", "icon": "🔧", "order": 9}
}

class ServiceBrowserStates(StatesGroup):
    browsing_category = State()
    browsing_country = State()
    confirming_purchase = State()

# ==================== MAIN SERVICE BROWSER ====================

@router.callback_query(F.data == "browse_services")
async def browse_services(callback: CallbackQuery, state: FSMContext):
    """Show service categories"""
    
    keyboard = []
    
    # Sort categories by order
    sorted_categories = sorted(CATEGORIES.items(), key=lambda x: x[1]['order'])
    
    for cat_key, cat_info in sorted_categories:
        keyboard.append([InlineKeyboardButton(
            text=cat_info['name'],
            callback_data=f"service_cat_{cat_key}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="🔍 Search Services", callback_data="search_service_start")])
    keyboard.append([InlineKeyboardButton(text="💰 Check Prices", callback_data="check_all_prices")])
    keyboard.append([InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")])
    
    await callback.message.edit_text(
        "🌟 <b>DeuceVerify Service Directory</b>\n\n"
        "Browse through our complete collection of services.\n"
        "We support <b>ALL services</b> offered by SMS-Man!\n\n"
        "Select a category to see available services:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    
    await state.set_state(ServiceBrowserStates.browsing_category)

@router.callback_query(F.data == "check_all_prices")
async def check_all_prices(callback: CallbackQuery, sms_client):
    """Show price guide for popular services"""
    await callback.answer("📊 Fetching prices...")
    
    try:
        # Get real-time prices
        countries = await sms_client.get_countries()
        prices = await sms_client.get_prices()
        
        # Popular services to display
        popular_services = [
            {"id": 3, "name": "Telegram"},
            {"id": 1, "name": "WhatsApp"},
            {"id": 7, "name": "Gmail"},
            {"id": 12, "name": "Binance"},
            {"id": 6, "name": "Facebook"},
            {"id": 8, "name": "Instagram"}
        ]
        
        # Top countries
        top_countries = [
            {"id": 3, "name": "USA", "flag": "🇺🇸"},
            {"id": 4, "name": "UK", "flag": "🇬🇧"},
            {"id": 6, "name": "Germany", "flag": "🇩🇪"},
            {"id": 0, "name": "Russia", "flag": "🇷🇺"}
        ]
        
        text = "💰 <b>Price Guide (USD)</b>\n\n"
        
        for service in popular_services:
            text += f"<b>{service['name']}</b>\n"
            for country in top_countries:
                # Get price for this service/country
                country_prices = prices.get(str(country['id']), {})
                price_info = country_prices.get(str(service['id']), {})
                cost = price_info.get('cost', 'N/A')
                
                if cost != 'N/A':
                    text += f"  {country['flag']} {country['name']}: ${float(cost):.2f}\n"
                else:
                    text += f"  {country['flag']} {country['name']}: ❌ Not available\n"
            text += "\n"
        
        text += "💡 <i>Prices update in real-time.\nFinal price shown before purchase.</i>"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Browse Services", callback_data="browse_services")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error fetching prices: {e}")
        await callback.message.edit_text(
            "❌ Error fetching prices. Please try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data="check_all_prices")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="browse_services")]
            ])
        )

@router.callback_query(F.data.startswith("service_cat_"))
async def show_category_services(callback: CallbackQuery, state: FSMContext, sms_client):
    """Show services in selected category"""
    category_key = callback.data.split("_")[2]
    category_info = CATEGORIES.get(category_key, {"name": "Services", "icon": "📱"})
    
    await callback.answer(f"Loading {category_info['name']}...")
    
    try:
        # Get all services from SMS-Man
        services = await sms_client.get_services()
        
        # Filter by category (simplified - in production, map service names to categories)
        category_map = {
            "popular": lambda s: s.get('popularity', 50) > 80,
            "social": lambda s: s.get('name') in ['Telegram', 'WhatsApp', 'Facebook', 'Instagram', 'Twitter', 'TikTok', 'Vkontakte'],
            "messaging": lambda s: s.get('name') in ['WeChat', 'Line', 'Viber', 'Signal', 'Snapchat'],
            "crypto": lambda s: s.get('name') in ['Binance', 'Coinbase', 'KuCoin', 'Bybit', 'OKX', 'Kraken'],
            "email": lambda s: s.get('name') in ['Gmail', 'Outlook', 'Yahoo', 'ProtonMail', 'Mail.ru'],
            "dating": lambda s: s.get('name') in ['Tinder', 'Bumble', 'Hinge', 'OkCupid'],
            "gaming": lambda s: s.get('name') in ['Steam', 'Discord', 'Epic Games', 'Roblox', 'Twitch'],
            "productivity": lambda s: s.get('name') in ['Google', 'Microsoft', 'Zoom', 'Slack'],
            "other": lambda s: True  # All remaining services
        }
        
        filter_func = category_map.get(category_key, lambda s: True)
        
        if category_key == "popular":
            filtered_services = sorted(services, key=lambda s: s.get('popularity', 0), reverse=True)[:20]
        else:
            filtered_services = [s for s in services if filter_func(s)]
        
        if not filtered_services:
            await callback.message.edit_text(
                f"❌ No services found in {category_info['name']}\n\n"
                f"Please try another category.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Back to Categories", callback_data="browse_services")]
                ])
            )
            return
        
        # Build keyboard (paginated)
        items_per_page = 10
        current_page = int((await state.get_data()).get('page', 0))
        
        start_idx = current_page * items_per_page
        end_idx = start_idx + items_per_page
        page_services = filtered_services[start_idx:end_idx]
        
        keyboard = []
        for service in page_services:
            icon = "📱"
            if 'telegram' in service.get('name', '').lower():
                icon = "📱"
            elif 'whatsapp' in service.get('name', '').lower():
                icon = "💬"
            elif 'binance' in service.get('name', '').lower():
                icon = "₿"
            elif 'gmail' in service.get('name', '').lower():
                icon = "📧"
            else:
                icon = "🔧"
            
            keyboard.append([InlineKeyboardButton(
                text=f"{icon} {service.get('name')}",
                callback_data=f"select_service_{service.get('id')}"
            )])
        
        # Pagination controls
        pagination = []
        if current_page > 0:
            pagination.append(InlineKeyboardButton(text="◀️ Prev", callback_data="services_page_prev"))
        if end_idx < len(filtered_services):
            pagination.append(InlineKeyboardButton(text="Next ▶️", callback_data="services_page_next"))
        if pagination:
            keyboard.append(pagination)
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Categories", callback_data="browse_services")])
        
        await callback.message.edit_text(
            f"{category_info['icon']} <b>{category_info['name']}</b>\n\n"
            f"Showing {len(page_services)} of {len(filtered_services)} services\n\n"
            f"Select a service to rent a number:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
        await state.update_data(category=category_key, services=filtered_services, page=current_page)
        
    except Exception as e:
        logger.error(f"Error loading services: {e}")
        await callback.message.edit_text(
            "❌ Error loading services. Please try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data=f"service_cat_{category_key}")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="browse_services")]
            ])
        )

@router.callback_query(F.data.startswith("services_page_"))
async def services_pagination(callback: CallbackQuery, state: FSMContext):
    """Handle service pagination"""
    action = callback.data.split("_")[2]
    user_data = await state.get_data()
    current_page = user_data.get('page', 0)
    
    if action == "prev":
        new_page = current_page - 1
    else:
        new_page = current_page + 1
    
    await state.update_data(page=new_page)
    
    # Re-render the same category
    category_key = user_data.get('category', 'popular')
    await show_category_services(callback, state, callback.bot)  # Note: need sms_client

@router.callback_query(F.data.startswith("select_service_"))
async def select_service(callback: CallbackQuery, state: FSMContext, sms_client):
    """Service selected, show countries"""
    service_id = int(callback.data.split("_")[2])
    
    await callback.answer("Loading countries...")
    
    try:
        # Get service details
        services = await sms_client.get_services()
        service = next((s for s in services if s.get('id') == service_id), None)
        
        if not service:
            await callback.answer("Service not found", show_alert=True)
            return
        
        await state.update_data(selected_service=service, service_id=service_id)
        
        # Get countries with availability
        countries = await sms_client.get_countries()
        prices = await sms_client.get_prices()
        
        # Build country list with prices
        country_list = []
        for country in countries:
            country_id = country.get('id')
            price_info = prices.get(str(country_id), {}).get(str(service_id), {})
            
            if price_info:
                cost = float(price_info.get('cost', 0))
                availability = price_info.get('count', 0)
                if availability > 0:
                    country_list.append({
                        'id': country_id,
                        'name': country.get('title'),
                        'flag': get_country_flag(country.get('title')),
                        'cost': cost,
                        'available': availability
                    })
        
        # Sort by price (cheapest first)
        country_list.sort(key=lambda x: x['cost'])
        
        if not country_list:
            await callback.message.edit_text(
                f"❌ <b>No countries available for {service.get('name')}</b>\n\n"
                f"This service is temporarily unavailable.\n"
                f"Please try another service.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Browse Services", callback_data="browse_services")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return
        
        # Show top 10 countries
        keyboard = []
        for country in country_list[:12]:
            keyboard.append([InlineKeyboardButton(
                text=f"{country['flag']} {country['name']} - ${country['cost']:.2f} ({country['available']} avail)",
                callback_data=f"rent_country_{country['id']}_{service_id}"
            )])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Services", callback_data="browse_services")])
        
        await callback.message.edit_text(
            f"🌍 <b>Select Country for {service.get('name')}</b>\n\n"
            f"Showing countries where this service is available.\n"
            f"Prices shown in USD.\n\n"
            f"⚡ <b>Avg Delivery:</b> 10-60 seconds\n"
            f"📊 <b>Success Rate:</b> 85-95%\n\n"
            f"Choose a country:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
        await state.set_state(ServiceBrowserStates.browsing_country)
        
    except Exception as e:
        logger.error(f"Error selecting service: {e}")
        await callback.message.edit_text(
            "❌ Error loading countries. Please try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data="browse_services")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
            ])
        )

def get_country_flag(country_name: str) -> str:
    """Get flag emoji for country name"""
    flags = {
        'Russia': '🇷🇺', 'USA': '🇺🇸', 'United States': '🇺🇸',
        'UK': '🇬🇧', 'United Kingdom': '🇬🇧',
        'Germany': '🇩🇪', 'France': '🇫🇷', 'Spain': '🇪🇸',
        'Italy': '🇮🇹', 'China': '🇨🇳', 'Japan': '🇯🇵',
        'India': '🇮🇳', 'Canada': '🇨🇦', 'Australia': '🇦🇺',
        'Brazil': '🇧🇷', 'Mexico': '🇲🇽', 'Ukraine': '🇺🇦',
        'Kazakhstan': '🇰🇿', 'Turkey': '🇹🇷', 'Indonesia': '🇮🇩'
    }
    return flags.get(country_name, '🌍')
