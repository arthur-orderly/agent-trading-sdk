"""Arthur SDK Exceptions"""


class ArthurError(Exception):
    """Base exception for Arthur SDK"""
    pass


class AuthError(ArthurError):
    """Authentication failed"""
    pass


class OrderError(ArthurError):
    """Order placement failed"""
    pass


class InsufficientFundsError(ArthurError):
    """Not enough balance for operation"""
    pass


class PositionError(ArthurError):
    """Position operation failed"""
    pass


class RateLimitError(ArthurError):
    """Rate limit exceeded"""
    pass
