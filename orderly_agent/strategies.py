"""
Agent Trading SDK Strategy Runner - Execute trading strategies from JSON configs.

Supports both simple single-symbol and multi-asset strategies (like Unlockoor).
"""

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Callable, Union
from pathlib import Path

from .client import Arthur, Position
from .exceptions import ArthurError


@dataclass
class Signal:
    """Trading signal from strategy evaluation"""
    action: str  # "long", "short", "close", "hold"
    symbol: str
    size: Optional[float] = None
    usd: Optional[float] = None
    reason: str = ""
    confidence: float = 1.0


@dataclass
class StrategyConfig:
    """Strategy configuration loaded from JSON - supports both simple and multi-asset formats"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    
    # Single symbol mode (simple strategies)
    symbol: Optional[str] = None
    
    # Multi-asset mode (Unlockoor-style)
    long_assets: List[str] = field(default_factory=list)
    short_assets: List[str] = field(default_factory=list)
    
    # Timeframe
    timeframe: str = "4h"
    
    # Signals config
    signals: Dict = field(default_factory=dict)
    
    # Risk management
    risk: Dict = field(default_factory=dict)
    
    # Position sizing
    position: Dict = field(default_factory=dict)
    
    # Execution settings
    execution: Dict = field(default_factory=dict)
    
    # Flags
    flags: Dict = field(default_factory=dict)
    
    @classmethod
    def from_file(cls, path: str) -> "StrategyConfig":
        """Load strategy from JSON file"""
        with open(Path(path).expanduser()) as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "StrategyConfig":
        """Create strategy from dict"""
        return cls(
            name=data.get("name", "Unnamed Strategy"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            symbol=data.get("symbol"),
            long_assets=data.get("long_assets", []),
            short_assets=data.get("short_assets", []),
            timeframe=data.get("timeframe") or data.get("signals", {}).get("timeframe", "4h"),
            signals=data.get("signals", {}),
            risk=data.get("risk", {}),
            position=data.get("position", {}),
            execution=data.get("execution", {}),
            flags=data.get("flags", {}),
        )
    
    @property
    def all_symbols(self) -> List[str]:
        """Get all tradeable symbols"""
        if self.symbol:
            return [self.symbol]
        return list(set(self.long_assets + self.short_assets))
    
    @property
    def is_multi_asset(self) -> bool:
        """Check if this is a multi-asset strategy"""
        return bool(self.long_assets or self.short_assets)
    
    @property
    def leverage(self) -> int:
        return self.position.get("leverage", 5)
    
    @property
    def position_size_pct(self) -> float:
        return self.position.get("size_pct", 10)
    
    @property
    def stop_loss_pct(self) -> Optional[float]:
        return self.risk.get("stop_loss_pct")
    
    @property
    def take_profit_pct(self) -> Optional[float]:
        return self.risk.get("take_profit_pct")
    
    @property
    def max_positions(self) -> int:
        return self.risk.get("max_positions", 5)
    
    @property
    def dry_run(self) -> bool:
        return self.flags.get("dry_run", False)
    
    @property
    def allow_shorts(self) -> bool:
        return self.flags.get("allow_shorts", True)


class StrategyRunner:
    """
    Execute trading strategies on Orderly Network.
    
    Supports:
    - Simple single-symbol strategies
    - Multi-asset strategies (Unlockoor-style with long_assets/short_assets)
    - RSI-based signals
    - Risk management (stop loss, take profit)
    
    Example:
        client = Arthur.from_credentials_file("creds.json")
        runner = StrategyRunner(client)
        
        # Run a strategy once
        result = runner.run("strategies/unlockoor.json")
    """
    
    def __init__(
        self,
        client: Arthur,
        dry_run: bool = False,
        on_signal: Optional[Callable[[Signal], None]] = None,
        on_trade: Optional[Callable[[Dict], None]] = None,
    ):
        """
        Initialize strategy runner.
        
        Args:
            client: Authenticated Arthur client
            dry_run: If True, don't execute trades (just log signals)
            on_signal: Callback when signal is generated
            on_trade: Callback when trade is executed
        """
        self.client = client
        self.dry_run = dry_run
        self.on_signal = on_signal
        self.on_trade = on_trade
        self._last_run: Dict[str, float] = {}
        self._rsi_cache: Dict[str, float] = {}
        self._rsi_cache_time: float = 0
        
    def run(
        self,
        strategy: Union[str, StrategyConfig, Dict],
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run a strategy once.
        
        Args:
            strategy: Path to JSON file, StrategyConfig, or dict
            force: Run even if not time for next check
            
        Returns:
            Dict with run results
        """
        # Load strategy config
        if isinstance(strategy, str):
            config = StrategyConfig.from_file(strategy)
        elif isinstance(strategy, dict):
            config = StrategyConfig.from_dict(strategy)
        else:
            config = strategy
        
        result = {
            "strategy": config.name,
            "version": config.version,
            "timestamp": int(time.time() * 1000),
            "signals": [],
            "trades": [],
            "errors": [],
            "dry_run": self.dry_run or config.dry_run,
        }
        
        try:
            # Check if it's time to run
            if not force and not self._should_run(config):
                result["skipped"] = True
                result["reason"] = "Not time for next check"
                return result
            
            # Get current positions
            positions = {p.symbol: p for p in self.client.positions()}
            
            # Multi-asset or single-symbol?
            if config.is_multi_asset:
                signals = self._evaluate_multi_asset(config, positions)
            else:
                signals = self._evaluate_single(config, positions)
            
            result["signals"] = [s.__dict__ for s in signals]
            
            # Execute signals
            for signal in signals:
                if self.on_signal:
                    self.on_signal(signal)
                
                if signal.action != "hold":
                    if self.dry_run or config.dry_run:
                        result["trades"].append({
                            "action": signal.action,
                            "symbol": signal.symbol,
                            "dry_run": True,
                            "reason": signal.reason,
                        })
                    else:
                        trade = self._execute(config, signal, positions.get(signal.symbol))
                        result["trades"].append(trade)
                        
                        if self.on_trade and trade:
                            self.on_trade(trade)
            
            self._last_run[config.name] = time.time()
            
        except Exception as e:
            result["errors"].append(str(e))
            
        return result
    
    def _should_run(self, config: StrategyConfig) -> bool:
        """Check if enough time has passed since last run"""
        last = self._last_run.get(config.name, 0)
        
        # Parse timeframe to seconds
        tf = config.timeframe.lower()
        if tf.endswith("m"):
            interval = int(tf[:-1]) * 60
        elif tf.endswith("h"):
            interval = int(tf[:-1]) * 3600
        elif tf.endswith("d"):
            interval = int(tf[:-1]) * 86400
        else:
            interval = 3600  # Default 1 hour
        
        return time.time() - last >= interval
    
    def _evaluate_multi_asset(
        self,
        config: StrategyConfig,
        positions: Dict[str, Position],
    ) -> List[Signal]:
        """Evaluate a multi-asset strategy (Unlockoor-style)"""
        signals = []
        
        # Get RSI for all assets
        rsi_values = self._get_rsi_batch(config.all_symbols, config.signals.get("period", 14))
        
        # Count current positions
        current_position_count = len([p for p in positions.values() if p.size > 0])
        
        # Check long assets
        for asset in config.long_assets:
            symbol = self._normalize_symbol(asset)
            rsi = rsi_values.get(symbol, 50)
            position = positions.get(symbol)
            
            signal = self._evaluate_asset(
                config=config,
                symbol=symbol,
                asset=asset,
                rsi=rsi,
                position=position,
                side="long",
                current_position_count=current_position_count,
            )
            signals.append(signal)
            
            if signal.action in ["long", "short"]:
                current_position_count += 1
        
        # Check short assets
        if config.allow_shorts:
            for asset in config.short_assets:
                symbol = self._normalize_symbol(asset)
                rsi = rsi_values.get(symbol, 50)
                position = positions.get(symbol)
                
                signal = self._evaluate_asset(
                    config=config,
                    symbol=symbol,
                    asset=asset,
                    rsi=rsi,
                    position=position,
                    side="short",
                    current_position_count=current_position_count,
                )
                signals.append(signal)
                
                if signal.action in ["long", "short"]:
                    current_position_count += 1
        
        return signals
    
    def _evaluate_asset(
        self,
        config: StrategyConfig,
        symbol: str,
        asset: str,
        rsi: float,
        position: Optional[Position],
        side: str,  # "long" or "short"
        current_position_count: int,
    ) -> Signal:
        """Evaluate a single asset within a multi-asset strategy"""
        
        long_entry = config.signals.get("long_entry", 30)
        short_entry = config.signals.get("short_entry", 70)
        
        # If we have a position, check for exit
        if position and position.size > 0:
            # Check stop loss
            if config.stop_loss_pct:
                if position.pnl_percent <= -config.stop_loss_pct:
                    return Signal(
                        action="close",
                        symbol=symbol,
                        reason=f"Stop loss hit: {position.pnl_percent:.1f}% (limit: -{config.stop_loss_pct}%)",
                    )
            
            # Check take profit
            if config.take_profit_pct:
                if position.pnl_percent >= config.take_profit_pct:
                    return Signal(
                        action="close",
                        symbol=symbol,
                        reason=f"Take profit hit: {position.pnl_percent:.1f}% (target: +{config.take_profit_pct}%)",
                    )
            
            # Check RSI exit
            if position.side == "LONG" and rsi >= 70:
                return Signal(
                    action="close",
                    symbol=symbol,
                    reason=f"RSI exit for long: {rsi:.1f} >= 70",
                )
            elif position.side == "SHORT" and rsi <= 30:
                return Signal(
                    action="close",
                    symbol=symbol,
                    reason=f"RSI exit for short: {rsi:.1f} <= 30",
                )
            
            # Hold position
            return Signal(
                action="hold",
                symbol=symbol,
                reason=f"Holding {position.side} position, RSI={rsi:.1f}, PnL={position.pnl_percent:.1f}%",
            )
        
        # No position - check for entry
        if current_position_count >= config.max_positions:
            return Signal(
                action="hold",
                symbol=symbol,
                reason=f"Max positions ({config.max_positions}) reached",
            )
        
        # Entry signals
        if side == "long" and rsi <= long_entry:
            return Signal(
                action="long",
                symbol=symbol,
                reason=f"Long entry: RSI {rsi:.1f} <= {long_entry}",
                confidence=1.0 - (rsi / 100),  # Higher confidence at lower RSI
            )
        elif side == "short" and rsi >= short_entry:
            return Signal(
                action="short",
                symbol=symbol,
                reason=f"Short entry: RSI {rsi:.1f} >= {short_entry}",
                confidence=rsi / 100,  # Higher confidence at higher RSI
            )
        
        # No signal
        return Signal(
            action="hold",
            symbol=symbol,
            reason=f"No entry signal: RSI={rsi:.1f} (long<={long_entry}, short>={short_entry})",
        )
    
    def _evaluate_single(
        self,
        config: StrategyConfig,
        positions: Dict[str, Position],
    ) -> List[Signal]:
        """Evaluate a simple single-symbol strategy"""
        symbol = self._normalize_symbol(config.symbol or "ETH")
        position = positions.get(symbol)
        
        # Get RSI
        rsi = self._get_rsi(symbol, config.signals.get("period", 14))
        
        signal = self._evaluate_asset(
            config=config,
            symbol=symbol,
            asset=config.symbol or "ETH",
            rsi=rsi,
            position=position,
            side="long",  # Default to long for simple strategies
            current_position_count=len(positions),
        )
        
        return [signal]
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Convert short symbol (ETH) to full symbol (PERP_ETH_USDC)"""
        symbol = symbol.upper()
        if symbol.startswith("PERP_"):
            return symbol
        return f"PERP_{symbol}_USDC"
    
    def _get_rsi(self, symbol: str, period: int = 14) -> float:
        """Get RSI for a symbol using Orderly's TradingView history endpoint"""
        try:
            # Calculate time range (need period + buffer days)
            now = int(time.time())
            days_needed = period + 5
            from_ts = now - (days_needed * 86400)
            
            # Use TV history endpoint
            url = f"https://api-evm.orderly.org/tv/history?symbol={symbol}&resolution=1D&from={from_ts}&to={now}"
            
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            
            if data.get("s") != "ok" or "c" not in data:
                return 50.0  # Default neutral RSI
            
            closes = data["c"]  # Already in chronological order
            
            if len(closes) < period + 1:
                return 50.0
            
            # Calculate RSI
            gains = []
            losses = []
            
            for i in range(1, len(closes)):
                change = closes[i] - closes[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            
            if len(gains) < period:
                return 50.0
            
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            
            if avg_loss == 0:
                return 100.0
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            print(f"Error getting RSI for {symbol}: {e}")
            return 50.0  # Default neutral
    
    def _get_rsi_batch(self, symbols: List[str], period: int = 14) -> Dict[str, float]:
        """Get RSI for multiple symbols"""
        # Use cache if fresh (< 5 minutes)
        if time.time() - self._rsi_cache_time < 300:
            return self._rsi_cache
        
        result = {}
        for symbol in symbols:
            full_symbol = self._normalize_symbol(symbol)
            result[full_symbol] = self._get_rsi(full_symbol, period)
            time.sleep(0.15)  # Rate limit
        
        self._rsi_cache = result
        self._rsi_cache_time = time.time()
        
        return result
    
    def _execute(
        self,
        config: StrategyConfig,
        signal: Signal,
        position: Optional[Position],
    ) -> Dict:
        """Execute a trading signal"""
        result = {
            "action": signal.action,
            "symbol": signal.symbol,
            "timestamp": int(time.time() * 1000),
            "reason": signal.reason,
        }
        
        try:
            # Set leverage
            self.client.set_leverage(signal.symbol, config.leverage)
            
            # Calculate position size
            balance = self.client.balance()
            size_usd = balance * (config.position_size_pct / 100)
            
            if signal.action == "long":
                order = self.client.buy(signal.symbol, usd=size_usd)
                result["order_id"] = order.order_id
                result["size"] = order.size
                result["status"] = "executed"
                
            elif signal.action == "short":
                order = self.client.sell(signal.symbol, usd=size_usd)
                result["order_id"] = order.order_id
                result["size"] = order.size
                result["status"] = "executed"
                
            elif signal.action == "close":
                order = self.client.close(signal.symbol)
                if order:
                    result["order_id"] = order.order_id
                    result["size"] = order.size
                result["status"] = "executed"
                
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            
        return result


# Convenience function
def run_strategy(
    strategy_path: str,
    credentials_path: str,
    dry_run: bool = False,
) -> Dict:
    """
    Run a strategy once (convenience function).
    
    Args:
        strategy_path: Path to strategy JSON
        credentials_path: Path to credentials JSON
        dry_run: Don't execute trades
        
    Returns:
        Run result dict
    """
    client = Arthur.from_credentials_file(credentials_path)
    runner = StrategyRunner(client, dry_run=dry_run)
    return runner.run(strategy_path)
