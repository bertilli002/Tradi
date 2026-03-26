    # ── /profile ──────────────────────────────────────────────────────────────
    async def cmd_profile(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        tg = update.effective_user
        user = await get_or_create_user(tg.id, tg.username, tg.full_name)
        
        await update.message.reply_text(
            f"👤 *Your Profile*\n\n"
            f"Name: `{tg.full_name}`\n"
            f"Username: @{tg.username or 'N/A'}\n"
            f"User ID: `{tg.id}`\n"
            f"Joined: {user.created_at.strftime('%Y-%m-%d')}\n\n"
            f"💰 Balance: `${user.balance:.2f} USDT`",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /support ──────────────────────────────────────────────────────────────
    async def cmd_support(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        # Replace 'YourSupportUsername' with your actual Telegram username
        await update.message.reply_text(
            "🆘 *Support*\n\n"
            "If you have issues with a deposit or withdrawal, please contact our support team:\n\n"
            "Contact: @YourSupportUsername\n\n"
            "Please include your User ID or Reference ID in your message.",
            parse_mode=ParseMode.MARKDOWN,
        )
