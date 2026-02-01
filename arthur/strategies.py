"""
Arthur SDK Strategy Runner - Execute trading strategies from JSON configs.

This replaces ATP (Agent Trading Protocol) executor with a cleaner Python implementation.
"""

import json
import time
from dataclasses import dataclass
from typing import Optional, Dict, List, Any, Callable, Union
from pathlib import Path

from .client import Arthur, Position
from .exceptions import ArthurError


@dataclass
class Signal:
    """Trading signal from strategy evaluation"""
    action: str  # "buy", "sell", "close", "hold"
    symbol: str
    size: Optional[float] = None
    usd: Optional[float] = None
    reason: str = ""
    confidence: float = 1.0


@dataclass
class StrategyConfig:
    """Strategy configuration loaded from JSON"""
    name: str
    symbol: str
    timeframe: str
    position_size_usd: float
    max_positions: int = 1
    leverage: int = 5
    
    # Entry conditions
    entry_long: Optional[Dict] = None
    entry_short: Optional[Dict] = None
    
    # Exit conditions  
    exit_long: Optional[Dict] = None
    exit_short: Optional[Dict] = None
    
    # Risk management
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    
    # Filters
    trading_hours: Optional[List[int]] = None  # UTC hours when trading allowed
    min_volume_24h: Optional[float] = None
    
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
            symbol=data.get("symbol", "PERP_ETH_USDC"),
            timeframe=data.get("timeframe", "4h"),
            position_size_usd=data.get("position_size_usd", 100),
            max_positions=data.get("max_positions", 1),
            leverage=data.get("leverage", 5),
            entry_long=data.get("entry_long"),
            entry_short=data.get("entry_short"),
            exit_long=data.get("exit_long"),
            exit_short=data.get("exit_short"),
            stop_loss_pct=data.get("stop_loss_pct"),
            take_profit_pct=data.get("take_profit_pct"),
            max_drawdown_pct=data.get("max_drawdown_pct"),
            trading_hours=data.get("trading_hours"),
            min_volume_24h=data.get("min_volume_24h"),
        )


class StrategyRunner:
    """
    Execute trading strategies on Orderly Network.
    
    Example:
        client = Arthur.from_credentials_file("creds.json")
        runner = StrategyRunner(client)
        
        # Run a strategy once
        result = runner.run("strategies/unlockoor.json")
        
        # Or run continuously
        runner.run_loop("strategies/unlockoor.json", interval=60)
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
            "symbol": config.symbol,
            "timestamp": int(time.time() * 1000),
            "signal": None,
            "trade": None,
            "error": None,
        }
        
        try:
            # Check if it's time to run
            if not force and not self._should_run(config):
                result["skipped"] = True
                result["reason"] = "Not time for next check"
                return result
            
            # Get current position
            position = self.client.position(config.symbol)
            
            # Evaluate strategy
            signal = self._evaluate(config, position)
            result["signal"] = signal.__dict__ if signal else None
            
            if self.on_signal and signal:
                self.on_signal(signal)
            
            # Execute if we have a signal
            if signal and signal.action != "hold":
                if self.dry_run:
                    result["dry_run"] = True
                else:
                    trade = self._execute(config, signal, position)
                    result["trade"] = trade
                    
                    if self.on_trade and trade:
                        self.on_trade(trade)
            
            self._last_run[config.name] = time.time()
            
        except Exception as e:
            result["error"] = str(e)
            
        return result
    
    def run_loop(
        self,
        strategy: Union[str, StrategyConfig, Dict],
        interval: int = 60,
        max_runs: Optional[int] = None,
    ):
        """
        Run strategy in a loop.
        
        Args:
            strategy: Strategy to run
            interval: Seconds between checks
            max_runs: Stop after this many runs (None = forever)
        """
        runs = 0
        while max_runs is None or runs < max_runs:
            result = self.run(strategy, force=True)
            print(f"[{time.strftime('%H:%M:%S')}] {result}")
            
            runs += 1
            if max_runs is None or runs < max_runs:
                time.sleep(interval)
    
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
    
    def _evaluate(
        self,
        config: StrategyConfig,
        position: Optional[Position],
    ) -> Optional[Signal]:
        """
        Evaluate strategy conditions and generate signal.
        
        This is a simplified evaluator. For complex conditions,
        override this method or use custom indicators.
        """
        symbol_short = config.symbol.replace("PERP_", "").replace("_USDC", "")
        
        # Check trading hours filter
        if config.trading_hours:
            current_hour = time.gmtime().tm_hour
            if current_hour not in config.trading_hours:
                return Signal(
                    action="hold",
                    symbol=config.symbol,
                    reason=f"Outside trading hours (current: {current_hour} UTC)"
                )
        
        # If we have a position, check exit conditions
        if position:
            # Check stop loss
            if config.stop_loss_pct:
                if position.pnl_percent <= -config.stop_loss_pct:
                    return Signal(
                        action="close",
                        symbol=config.symbol,
                        reason=f"Stop loss hit: {position.pnl_percent:.1f}%"
                    )
            
            # Check take profit
            if config.take_profit_pct:
                if position.pnl_percent >= config.take_profit_pct:
                    return Signal(
                        action="close",
                        symbol=config.symbol,
                        reason=f"Take profit hit: {position.pnl_percent:.1f}%"
                    )
            
            # Check exit conditions based on position side
            if position.side == "LONG" and config.exit_long:
                if self._check_condition(config.exit_long):
                    return Signal(
                        action="close",
                        symbol=config.symbol,
                        reason="Exit long condition met"
                    )
            elif position.side == "SHORT" and config.exit_short:
                if self._check_condition(config.exit_short):
                    return Signal(
                        action="close",
                        symbol=config.symbol,
                        reason="Exit short condition met"
                    )
        
        else:
            # No position - check entry conditions
            if config.entry_long and self._check_condition(config.entry_long):
                return Signal(
                    action="buy",
                    symbol=config.symbol,
                    usd=config.position_size_usd,
                    reason="Entry long condition met"
                )
            
            if config.entry_short and self._check_condition(config.entry_short):
                return Signal(
                    action="sell",
                    symbol=config.symbol,
                    usd=config.position_size_usd,
                    reason="Entry short condition met"
                )
        
        return Signal(
            action="hold",
            symbol=config.symbol,
            reason="No conditions met"
        )
    
    def _check_condition(self, condition: Dict) -> bool:
        """
        Check if a condition is met.
        
        Simple implementation - extend for complex indicators.
        Condition format: {"type": "always"} or {"type": "manual", "value": true}
        """
        cond_type = condition.get("type", "manual")
        
        if cond_type == "always":
            return True
        elif cond_type == "never":
            return False
        elif cond_type == "manual":
            return condition.get("value", False)
        # Add more condition types as needed (RSI, MA cross, etc.)
        
        return False
    
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
        }
        
        try:
            # Set leverage first
            self.client.set_leverage(config.symbol, config.leverage)
            
            if signal.action == "buy":
                order = self.client.buy(
                    signal.symbol,
                    usd=signal.usd or config.position_size_usd,
                )
                result["order_id"] = order.order_id
                result["size"] = order.size
                result["status"] = "executed"
                
            elif signal.action == "sell":
                order = self.client.sell(
                    signal.symbol,
                    usd=signal.usd or config.position_size_usd,
                )
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


# Convenience functions

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
