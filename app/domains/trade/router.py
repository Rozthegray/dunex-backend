import os
import httpx
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional

from app.db.session import get_db
from app.core.security import get_current_user
from app.domains.users.models import User
from app.domains.wallet.models import Wallet, LedgerTransaction  # 🚨 INJECTED LEDGER
from app.domains.trade.models import SubWallet, TradeExecution

router = APIRouter(
    prefix="/trade",
    tags=["Trading Engine"],
    dependencies=[Depends(get_current_user)]
)

# ─── Request models ────────────────────────────────────────────────────────────

class TradeRequest(BaseModel):
    symbol: str
    amount_usd: float = Field(..., gt=0, description="Must be greater than zero")
    trade_type: str  # "BUY" | "SELL"

class ActiveTradeRequest(BaseModel):
    symbol: str
    amount_crypto: float  # Negative = wager deduction, Positive = payout

# ─── Static fallback prices (used when both APIs fail) ────────────────────────

FALLBACK_MARKET = [
    {"symbol": "BTC",  "name": "Bitcoin",  "pair": "BTC/USD",  "current_price": 65430.50, "price_change_percent":  2.34, "high_24h": 66000.0, "low_24h": 64000.0, "volume": 1_200_500.0},
    {"symbol": "ETH",  "name": "Ethereum", "pair": "ETH/USD",  "current_price":  3450.20, "price_change_percent": -1.20, "high_24h":  3500.0, "low_24h":  3400.0, "volume": 5_600_000.0},
    {"symbol": "SOL",  "name": "Solana",   "pair": "SOL/USD",  "current_price":   145.75, "price_change_percent":  5.67, "high_24h":   150.0, "low_24h":   138.0, "volume":   25_000.0},
    {"symbol": "BNB",  "name": "BNB",      "pair": "BNB/USD",  "current_price":   590.10, "price_change_percent":  0.45, "high_24h":   600.0, "low_24h":   585.0, "volume":    4_000.0},
    {"symbol": "XRP",  "name": "XRP",      "pair": "XRP/USD",  "current_price":     0.58, "price_change_percent": -0.15, "high_24h":     0.60, "low_24h":     0.55, "volume":  150_000.0},
    {"symbol": "ADA",  "name": "Cardano",  "pair": "ADA/USD",  "current_price":     0.45, "price_change_percent":  1.10, "high_24h":     0.47, "low_24h":     0.43, "volume":   30_000.0},
    {"symbol": "DOGE", "name": "Dogecoin", "pair": "DOGE/USD", "current_price":     0.12, "price_change_percent": -0.90, "high_24h":     0.13, "low_24h":     0.11, "volume":   90_000.0},
    {"symbol": "AVAX", "name": "Avalanche","pair": "AVAX/USD", "current_price":    35.20, "price_change_percent":  3.20, "high_24h":    36.00, "low_24h":    34.00, "volume":    5_500.0},
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _cmc_headers() -> dict:
    api_key = os.getenv("CMC_API_KEY", "")
    if not api_key:
        raise ValueError("CMC_API_KEY environment variable not set.")
    return {"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"}

async def _fetch_live_price(symbol: str) -> float:
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers=_cmc_headers(),
                params={"symbol": symbol, "convert": "USD"},
                timeout=4.0,
            )
            res.raise_for_status()
            data = res.json()["data"]
            if symbol in data:
                return float(data[symbol]["quote"]["USD"]["price"])
    except Exception:
        pass

    try:
        slug_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binance-coin", "XRP": "xrp", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche", "DOT": "polkadot"}
        slug = slug_map.get(symbol, symbol.lower())
        async with httpx.AsyncClient() as client:
            res = await client.get(f"https://api.coincap.io/v2/assets/{slug}", timeout=3.0)
            res.raise_for_status()
            return float(res.json()["data"]["priceUsd"])
    except Exception:
        pass

    fallback = next((c for c in FALLBACK_MARKET if c["symbol"] == symbol), None)
    if fallback:
        return fallback["current_price"]
    raise HTTPException(status_code=400, detail=f"Price data unavailable for {symbol}.")


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/market")
async def get_live_market_data():
    try:
        symbols = ",".join(c["symbol"] for c in FALLBACK_MARKET)
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                headers=_cmc_headers(),
                params={"symbol": symbols, "convert": "USD"},
                timeout=5.0,
            )
            res.raise_for_status()
            cmc_data = res.json()["data"]

        market = []
        for fallback in FALLBACK_MARKET:
            sym = fallback["symbol"]
            coin = cmc_data.get(sym)
            if not coin:
                market.append(fallback)
                continue
            q = coin["quote"]["USD"]
            market.append({
                "symbol": sym,
                "name": coin.get("name", sym),
                "pair": f"{sym}/USD",
                "current_price": float(q["price"]),
                "price_change_percent": float(q.get("percent_change_24h", 0)),
                "high_24h": float(q["price"]) * 1.05, 
                "low_24h": float(q["price"]) * 0.95,
                "volume": float(q.get("volume_24h", 0)),
                "market_cap": float(q.get("market_cap", 0)),
            })
        return market
    except Exception:
        pass

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://api.coincap.io/v2/assets?limit=20", timeout=3.0)
            res.raise_for_status()
            coincap_data = {c["symbol"]: c for c in res.json()["data"]}

        market = []
        for fallback in FALLBACK_MARKET:
            sym = fallback["symbol"]
            coin = coincap_data.get(sym)
            if not coin:
                market.append(fallback)
                continue
            price = float(coin["priceUsd"])
            market.append({
                "symbol": sym,
                "name": coin.get("name", sym),
                "pair": f"{sym}/USD",
                "current_price": price,
                "price_change_percent": float(coin.get("changePercent24Hr", 0)),
                "high_24h": price * 1.05,
                "low_24h": price * 0.95,
                "volume": float(coin.get("volumeUsd24Hr", 0)),
            })
        return market
    except Exception:
        pass

    return FALLBACK_MARKET


@router.get("/history")
async def get_trade_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(TradeExecution)
        .where(TradeExecution.user_id == current_user.id)
        .order_by(TradeExecution.created_at.desc())
    )
    result = await db.execute(query)
    trades = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "pair": t.pair,
            "trade_type": t.trade_type,
            "amount_usd": float(t.amount_usd),
            "amount_crypto": float(t.amount_crypto),
            "entry_price": float(t.entry_price),
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
        for t in trades
    ]


@router.post("/execute")
async def execute_trade(
    payload: TradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SPOT TRADE: Swaps USD ↔ Crypto AND records the action in the main Wallet Ledger.
    """
    trade_type = payload.trade_type.upper()
    if trade_type not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="trade_type must be BUY or SELL.")

    current_price = await _fetch_live_price(payload.symbol)
    crypto_amount = payload.amount_usd / current_price

    usd_wallet = (await db.execute(select(Wallet).where(Wallet.user_id == current_user.id).with_for_update())).scalar_one_or_none()
    if not usd_wallet:
        raise HTTPException(status_code=400, detail="USD wallet not found.")

    sub_wallet = (await db.execute(select(SubWallet).where(SubWallet.user_id == current_user.id, SubWallet.symbol == payload.symbol).with_for_update())).scalar_one_or_none()
    if not sub_wallet:
        sub_wallet = SubWallet(user_id=current_user.id, symbol=payload.symbol, balance=0.0)
        db.add(sub_wallet)

    try:
        ledger_amount = 0.0

        if trade_type == "BUY":
            if float(usd_wallet.cached_balance) < payload.amount_usd:
                raise HTTPException(status_code=400, detail="Insufficient USD balance.")
            usd_wallet.cached_balance = float(usd_wallet.cached_balance) - payload.amount_usd
            sub_wallet.balance = float(sub_wallet.balance) + crypto_amount
            ledger_amount = -payload.amount_usd  # Deduction from main wallet
        else:  # SELL
            if float(sub_wallet.balance) < crypto_amount:
                raise HTTPException(status_code=400, detail=f"Insufficient {payload.symbol}.")
            sub_wallet.balance = float(sub_wallet.balance) - crypto_amount
            usd_wallet.cached_balance = float(usd_wallet.cached_balance) + payload.amount_usd
            ledger_amount = payload.amount_usd  # Addition to main wallet

        # 🚨 NEW: Log this trade directly into the Wallet Ledger so the user sees the money move
        ledger = LedgerTransaction(
            wallet_id=usd_wallet.id,
            amount=ledger_amount,
            transaction_type="spot_trade",
            status="completed",
            reference=f"SPOT-{uuid.uuid4().hex[:8].upper()}",
            destination_details=f"{trade_type} {payload.symbol}"
        )
        db.add(ledger)

        log = TradeExecution(
            user_id=current_user.id,
            pair=f"{payload.symbol}/USD",
            trade_type=trade_type,
            amount_usd=payload.amount_usd,
            amount_crypto=crypto_amount,
            entry_price=current_price,
            status="completed",
        )
        db.add(log)
        
        await db.commit()
        await db.refresh(usd_wallet)

        return {
            "status": "success",
            "trade_type": trade_type,
            "symbol": payload.symbol,
            "amount_usd": payload.amount_usd,
            "new_usd_balance": float(usd_wallet.cached_balance),
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio")
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    usd_wallet = (await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))).scalar_one_or_none()
    sub_wallets = (await db.execute(select(SubWallet).where(SubWallet.user_id == current_user.id, SubWallet.balance > 0))).scalars().all()

    price_map: dict[str, float] = {c["symbol"]: c["current_price"] for c in FALLBACK_MARKET}
    try:
        market = await get_live_market_data()
        price_map = {c["symbol"]: c["current_price"] for c in market}
    except Exception:
        pass

    assets = []
    for sw in sub_wallets:
        price = price_map.get(sw.symbol, 0.0)
        assets.append({
            "symbol": sw.symbol,
            "balance": float(sw.balance),
            "current_price": price,
            "value_usd": float(sw.balance) * price,
        })

    usd_balance = float(usd_wallet.cached_balance) if usd_wallet else 0.0
    total_value = usd_balance + sum(a["value_usd"] for a in assets)

    return {
        "usd_balance": usd_balance,
        "total_value_usd": total_value,
        "assets": assets,
    }


@router.post("/active/adjust")
async def active_trade_adjust(
    payload: ActiveTradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ACTIVE TRADE SETTLEMENT: 
    When the timer hits zero, physically moves USD payout to the main wallet and logs it.
    """
    try:
        current_price = await _fetch_live_price(payload.symbol)
        
        # Lock both wallets
        usd_wallet = (await db.execute(select(Wallet).where(Wallet.user_id == current_user.id).with_for_update())).scalar_one_or_none()
        sub_wallet = (await db.execute(select(SubWallet).where(SubWallet.user_id == current_user.id, SubWallet.symbol == payload.symbol).with_for_update())).scalar_one_or_none()

        if not usd_wallet:
            raise HTTPException(status_code=400, detail="Main USD wallet not found.")
        if not sub_wallet:
            sub_wallet = SubWallet(user_id=current_user.id, symbol=payload.symbol, balance=0.0)
            db.add(sub_wallet)

        action = "ACTIVE_CLOSE" if payload.amount_crypto > 0 else "ACTIVE_START"

        if action == "ACTIVE_START":
            # Starting the trade: Deduct the crypto wager
            if sub_wallet.balance < abs(payload.amount_crypto):
                raise HTTPException(status_code=400, detail=f"Insufficient {payload.symbol} locked for this trade.")
            sub_wallet.balance += payload.amount_crypto # Payload is negative
            
        else:
            # 🚨 NEW: Closing the trade: Pay the profit DIRECTLY into the Main USD Wallet
            payout_usd = payload.amount_crypto * current_price
            usd_wallet.cached_balance += payout_usd
            
            # 🚨 NEW: Create the Ledger Receipt so it shows up in history
            ledger = LedgerTransaction(
                wallet_id=usd_wallet.id,
                amount=payout_usd,
                transaction_type="trade_settlement",
                status="completed",
                reference=f"SETTLE-{uuid.uuid4().hex[:8].upper()}",
                destination_details=f"Active {payload.symbol} Settlement"
            )
            db.add(ledger)

        # Log the execution
        log = TradeExecution(
            user_id=current_user.id,
            pair=f"{payload.symbol}/USD",
            trade_type=action,
            amount_usd=abs(payload.amount_crypto * current_price),
            amount_crypto=payload.amount_crypto,
            entry_price=current_price,
            status="completed",
        )
        db.add(log)
        
        await db.commit()
        await db.refresh(usd_wallet)
        await db.refresh(sub_wallet)

        return {
            "status": "success", 
            "action": action, 
            "new_crypto_balance": float(sub_wallet.balance),
            "new_usd_balance": float(usd_wallet.cached_balance)
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
