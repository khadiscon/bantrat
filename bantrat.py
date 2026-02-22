"""
bantrat Telegram Bot
Each user provides their own Bankr API key on first use.
Commands:
  /start          - Welcome + API key setup
  /setkey         - Update your Bankr API key
  /deploy         - Deploy a new token
  /simulate       - Simulate a deploy (no tx)
  /portfolio      - Check wallet portfolio
  /fees           - Check claimable fees
  /claimfees      - Claim your fees
  /token <addr>   - Look up token info
  /help           - Show all commands
"""

import os
import json
import logging
import requests
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Your token has been added as the default fallback here
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8403134981:AAEyf6EBA2YDuz_PHG_sVnRt6TP6lcdhyYI")
BANKR_BASE_URL = "https://api.bankr.bot"
KEYS_FILE = "user_keys.json"

(
    AWAIT_API_KEY,
    DEPLOY_NAME,
    DEPLOY_SYMBOL,
    DEPLOY_DESC,
    DEPLOY_IMAGE,
    DEPLOY_CONFIRM,
) = range(6)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_keys() -> dict:
    if Path(KEYS_FILE).exists():
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_key(user_id: int, api_key: str):
    keys = load_keys()
    keys[str(user_id)] = api_key
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f)


def get_key(user_id: int):
    return load_keys().get(str(user_id))


def bankr_post(endpoint: str, payload: dict, api_key: str) -> dict:
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    try:
        r = requests.post(f"{BANKR_BASE_URL}{endpoint}", json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError:
        return {"error": r.json().get("message", r.text)}
    except Exception as e:
        return {"error": str(e)}


def bankr_get(endpoint: str, api_key: str) -> dict:
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    try:
        r = requests.get(f"{BANKR_BASE_URL}{endpoint}", headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError:
        return {"error": r.json().get("message", r.text)}
    except Exception as e:
        return {"error": str(e)}


def fmt_fee_dist(dist: dict) -> str:
    lines = []
    for role, info in dist.items():
        pct = info["bps"] / 100
        lines.append(f"  • {role.capitalize()}: {pct}% → `{info['address'][:10]}...`")
    return "\n".join(lines)


async def require_key(update: Update):
    key = get_key(update.effective_user.id)
    if not key:
        await update.message.reply_text(
            "🔑 You haven't set your Bankr API key yet.\n\nUse /setkey to add it and get started!"
        )
        return None
    return key


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing_key = get_key(user_id)

    if existing_key:
        await update.message.reply_text(
            "👾 *bantrat*\n\nWelcome back! Your Bankr API key is already set.\n\n"
            "Commands:\n"
            "  /deploy — Deploy a new token\n"
            "  /simulate — Simulate a deploy\n"
            "  /portfolio — Check your portfolio\n"
            "  /fees — View claimable fees\n"
            "  /claimfees — Claim your fees\n"
            "  /token <address> — Look up a token\n"
            "  /setkey — Update your API key\n"
            "  /help — Show this menu",
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "👾 *Welcome to bantrat!*\n\n"
            "Your on-chain security sentinel — deploying tokens, scanning fees, protecting the claw.\n\n"
            "To get started, I need your *Bankr API key*.\n\n"
            "👉 Get one at [bankr.bot/api](https://bankr.bot/api) — make sure *Agent API access* is enabled.\n\n"
            "Send your API key now:",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return AWAIT_API_KEY


async def setkey_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔑 Send your new Bankr API key now.\n\n⚠️ Keep it private — don't share it with anyone.",
    )
    return AWAIT_API_KEY


async def receive_api_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    api_key = update.message.text.strip()

    if not api_key.startswith("bk_") or len(api_key) < 10:
        await update.message.reply_text(
            "❌ That doesn't look like a valid Bankr API key.\nIt should start with `bk_`. Please try again.",
            parse_mode="Markdown",
        )
        return AWAIT_API_KEY

    await update.message.reply_text("⏳ Verifying your API key...")
    test = bankr_post("/token-launches/deploy", {"tokenName": "test", "simulateOnly": True}, api_key)

    if "error" in test and "auth" in str(test["error"]).lower():
        await update.message.reply_text("❌ Invalid API key. Please check and try again.")
        return AWAIT_API_KEY

    save_key(update.effective_user.id, api_key)
    await update.message.reply_text(
        "✅ *API key saved!* You're all set.\n\nUse /help to see what I can do.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👾 *bantrat — Commands*\n\n"
        "  /deploy — Deploy a new token\n"
        "  /simulate — Simulate a deploy\n"
        "  /portfolio — Check your portfolio\n"
        "  /fees — View claimable fees\n"
        "  /claimfees — Claim your fees\n"
        "  /token <address> — Look up a token\n"
        "  /setkey — Update your Bankr API key\n"
        "  /cancel — Cancel current action",
        parse_mode="Markdown",
    )


async def deploy_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await require_key(update):
        return ConversationHandler.END
    ctx.user_data.clear()
    ctx.user_data["simulate"] = False
    await update.message.reply_text("🚀 *Token Deploy*\n\nWhat's the token name?", parse_mode="Markdown")
    return DEPLOY_NAME


async def simulate_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await require_key(update):
        return ConversationHandler.END
    ctx.user_data.clear()
    ctx.user_data["simulate"] = True
    await update.message.reply_text("🔬 *Simulate Deploy*\n\nWhat's the token name?", parse_mode="Markdown")
    return DEPLOY_NAME


async def deploy_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Token symbol? (e.g. CLAW) — or type `skip` to auto-generate")
    return DEPLOY_SYMBOL


async def deploy_symbol(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["symbol"] = None if val.lower() == "skip" else val.upper()
    await update.message.reply_text("Short description? — or type `skip`")
    return DEPLOY_DESC


async def deploy_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["desc"] = None if val.lower() == "skip" else val
    await update.message.reply_text("Image URL? — or type `skip`")
    return DEPLOY_IMAGE


async def deploy_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["image"] = None if val.lower() == "skip" else val

    d = ctx.user_data
    simulate = d.get("simulate", False)
    summary = (
        f"*{'[SIMULATE] ' if simulate else ''}Ready to deploy:*\n\n"
        f"  Name: `{d['name']}`\n"
        f"  Symbol: `{d['symbol'] or 'auto'}`\n"
        f"  Description: {d['desc'] or '_none_'}\n"
        f"  Image: {d['image'] or '_none_'}\n\n"
        "Type `confirm` to proceed or `cancel` to abort."
    )
    await update.message.reply_text(summary, parse_mode="Markdown")
    return DEPLOY_CONFIRM


async def deploy_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text != "confirm":
        await update.message.reply_text("❌ Deploy cancelled.")
        ctx.user_data.clear()
        return ConversationHandler.END

    api_key = get_key(update.effective_user.id)
    d = ctx.user_data
    payload = {"tokenName": d["name"], "simulateOnly": d.get("simulate", False)}
    if d.get("symbol"):
        payload["tokenSymbol"] = d["symbol"]
    if d.get("desc"):
        payload["description"] = d["desc"]
    if d.get("image"):
        payload["image"] = d["image"]

    await update.message.reply_text("⏳ Deploying... please wait.")
    result = bankr_post("/token-launches/deploy", payload, api_key)

    if "error" in result:
        await update.message.reply_text(f"❌ Error: {result['error']}")
    elif result.get("success"):
        simulated = result.get("simulated", False)
        msg = f"{'🔬 Simulated' if simulated else '✅ Deployed'} *{d['name']}*\n\n  Contract: `{result['tokenAddress']}`\n"
        if not simulated:
            msg += (
                f"  Pool ID: `{result['poolId'][:20]}...`\n"
                f"  TX: `{result['txHash'][:20]}...`\n"
                f"  Chain: {result['chain']}\n\n"
                f"*Fee Distribution:*\n{fmt_fee_dist(result['feeDistribution'])}\n\n"
                f"🔍 [View on Basescan](https://basescan.org/address/{result['tokenAddress']})"
            )
        await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await update.message.reply_text("⚠️ Unexpected response. Check logs.")

    ctx.user_data.clear()
    return ConversationHandler.END


async def deploy_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    ctx.user_data.clear()
    return ConversationHandler.END


async def portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    api_key = await require_key(update)
    if not api_key:
        return
    await update.message.reply_text("⏳ Fetching portfolio...")
    result = bankr_get("/portfolio", api_key)
    if "error" in result:
        await update.message.reply_text(f"❌ Error: {result['error']}")
        return
    await update.message.reply_text(f"💼 *Portfolio*\n\n```{str(result)[:1000]}```", parse_mode="Markdown")


async def fees(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    api_key = await require_key(update)
    if not api_key:
        return
    await update.message.reply_text("⏳ Fetching claimable fees...")
    result = bankr_get("/token-launches/fees", api_key)
    if "error" in result:
        await update.message.reply_text(f"❌ Error: {result['error']}")
        return
    await update.message.reply_text(f"💰 *Claimable Fees*\n\n```{str(result)[:1000]}```", parse_mode="Markdown")


async def claimfees(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    api_key = await require_key(update)
    if not api_key:
        return
    await update.message.reply_text("⏳ Claiming fees...")
    result = bankr_post("/token-launches/fees/claim", {}, api_key)
    if "error" in result:
        await update.message.reply_text(f"❌ Error: {result['error']}")
        return
    await update.message.reply_text(f"✅ *Fees Claimed!*\n\n```{str(result)[:1000]}```", parse_mode="Markdown")


async def token_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    api_key = await require_key(update)
    if not api_key:
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/token <contract_address>`", parse_mode="Markdown")
        return
    address = ctx.args[0].strip()
    await update.message.reply_text(f"⏳ Looking up `{address[:10]}...`", parse_mode="Markdown")
    result = bankr_get(f"/token-launches/{address}", api_key)
    if "error" in result:
        await update.message.reply_text(f"❌ Error: {result['error']}")
        return
    await update.message.reply_text(f"🔍 *Token Info*\n\n```{str(result)[:1000]}```", parse_mode="Markdown")


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    onboard_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("setkey", setkey_start),
        ],
        states={
            AWAIT_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_api_key)],
        },
        fallbacks=[CommandHandler("cancel", deploy_cancel)],
    )

    deploy_conv = ConversationHandler(
        entry_points=[
            CommandHandler("deploy", deploy_start),
            CommandHandler("simulate", simulate_start),
        ],
        states={
            DEPLOY_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_name)],
            DEPLOY_SYMBOL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_symbol)],
            DEPLOY_DESC:    [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_desc)],
            DEPLOY_IMAGE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_image)],
            DEPLOY_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, deploy_confirm)],
        },
        fallbacks=[CommandHandler("cancel", deploy_cancel)],
    )

    app.add_handler(onboard_conv)
    app.add_handler(deploy_conv)
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("portfolio", portfolio))
    app.add_handler(CommandHandler("fees", fees))
    app.add_handler(CommandHandler("claimfees", claimfees))
    app.add_handler(CommandHandler("token", token_info))

    logger.info("bantrat is running...")
    app.run_polling()


if __name__ == "__main__":
    main()