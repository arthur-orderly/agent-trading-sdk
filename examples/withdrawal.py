"""
Withdrawal Example - How to withdraw funds from Orderly

This example shows how to:
1. Check your balance
2. Withdraw USDC to your wallet
3. Check withdrawal status

Requirements:
    pip install eth-account  # For EIP-712 signing
"""

from orderly_agent import Arthur

# Initialize client with wallet for withdrawals
client = Arthur(
    api_key="ed25519:YOUR_API_KEY",
    secret_key="YOUR_SECRET_KEY",
    account_id="0x...",
    wallet_private_key="YOUR_WALLET_PRIVATE_KEY",  # Required for withdrawals!
    chain_id=42161,  # Arbitrum One
)

# Or load from files
# client = Arthur.from_credentials_file(
#     "credentials.json",
#     wallet_file="wallet.json",  # Contains privateKey
#     chain_id=42161,
# )

# Check balance first
balance = client.balance()
print(f"Available balance: {balance:.2f} USDC")

# Withdraw 100 USDC to Arbitrum One (default chain)
if balance >= 100:
    result = client.withdraw(100)
    print(f"Withdrawal submitted!")
    print(f"  ID: {result['withdraw_id']}")
    print(f"  Amount: {result['amount']} {result['token']}")
    print(f"  Chain: {result['chain_id']}")
    print(f"  Receiver: {result['receiver']}")
else:
    print(f"Insufficient balance for withdrawal")

# Withdraw to a different chain (e.g., Optimism)
# result = client.withdraw(50, to_chain_id=10)

# Withdraw to a specific address
# result = client.withdraw(50, receiver="0x...")

# Check withdrawal history
print("\nRecent withdrawals:")
for w in client.withdrawal_history(limit=5):
    print(f"  {w['id']}: {w['amount']:.2f} {w['token']} - {w['status']}")

# Check specific withdrawal status
# status = client.withdrawal_status("your_withdraw_id")
# print(f"Status: {status['status']}")

"""
Withdrawal Statuses:
- PENDING: Just submitted
- PENDING_REBALANCE: Cross-chain rebalancing in progress
- COMPLETED: Funds sent on-chain
- FAILED: Withdrawal failed

Supported Chains:
- 42161: Arbitrum One
- 10: Optimism
- 8453: Base
- 56: BNB Smart Chain
- 324: zkSync Era
- 534352: Scroll
- 81457: Blast
- Many more...
"""
