#!/usr/bin/env python3
"""
Migrate funds from Orderly broker to Arthur broker.

Steps:
1. Withdraw USDC from Orderly broker account
2. Wait for on-chain withdrawal
3. Deposit USDC to Arthur broker account
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data

# Arbitrum mainnet
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"
ARBITRUM_CHAIN_ID = 42161

# Orderly contracts on Arbitrum
USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  # Native USDC on Arbitrum
ORDERLY_VAULT = "0x816f722424B49Cf1275cc86DA9840Fbd5a6167e9"  # Orderly Vault on Arbitrum

# EIP-712 domain for Orderly
ORDERLY_DOMAIN = {
    "name": "Orderly",
    "version": "1",
    "chainId": ARBITRUM_CHAIN_ID,
    "verifyingContract": "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC"
}

def load_json(path):
    with open(Path(path).expanduser()) as f:
        return json.load(f)


def get_withdrawal_nonce(api_key, secret_key, account_id):
    """Get withdrawal nonce from Orderly"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from orderly_agent.auth import generate_auth_headers
    
    path = "/v1/withdraw_nonce"
    headers = generate_auth_headers(
        api_key=api_key,
        secret_key=secret_key,
        account_id=account_id,
        method="GET",
        path=path
    )
    
    req = urllib.request.Request(
        f"https://api-evm.orderly.org{path}",
        headers=headers
    )
    
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        
    if result.get('success'):
        return result['data']['withdraw_nonce']
    raise Exception(f"Failed to get nonce: {result}")


def create_withdrawal_request(api_key, secret_key, account_id, wallet_private_key, amount_usdc, broker_id="orderly"):
    """Create and sign withdrawal request"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from orderly_agent.auth import generate_auth_headers
    
    # Get nonce
    nonce = get_withdrawal_nonce(api_key, secret_key, account_id)
    print(f"  Withdrawal nonce: {nonce}")
    
    # Get wallet address from private key
    account = Account.from_key(wallet_private_key)
    wallet_address = account.address
    
    timestamp = int(time.time() * 1000)
    
    # Amount in USDC units (6 decimals)
    amount_raw = int(amount_usdc * 1_000_000)
    
    # EIP-712 typed data for withdrawal
    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"}
            ],
            "Withdraw": [
                {"name": "brokerId", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "receiver", "type": "address"},
                {"name": "token", "type": "string"},
                {"name": "amount", "type": "uint256"},
                {"name": "withdrawNonce", "type": "uint64"},
                {"name": "timestamp", "type": "uint64"}
            ]
        },
        "primaryType": "Withdraw",
        "domain": ORDERLY_DOMAIN,
        "message": {
            "brokerId": broker_id,
            "chainId": ARBITRUM_CHAIN_ID,
            "receiver": wallet_address,
            "token": "USDC",
            "amount": amount_raw,
            "withdrawNonce": nonce,
            "timestamp": timestamp
        }
    }
    
    # Sign with wallet private key
    signable = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(signable, wallet_private_key)
    signature = signed.signature.hex()
    
    print(f"  Signed withdrawal for {amount_usdc} USDC")
    
    # Submit withdrawal request
    path = "/v1/withdraw_request"
    body = {
        "signature": signature,
        "userAddress": wallet_address,
        "verifyingContract": ORDERLY_DOMAIN["verifyingContract"],
        "message": {
            "brokerId": broker_id,
            "chainId": ARBITRUM_CHAIN_ID,
            "receiver": wallet_address,
            "token": "USDC",
            "amount": str(amount_raw),
            "withdrawNonce": nonce,
            "timestamp": timestamp
        }
    }
    
    body_str = json.dumps(body)
    
    headers = generate_auth_headers(
        api_key=api_key,
        secret_key=secret_key,
        account_id=account_id,
        method="POST",
        path=path,
        body=body_str
    )
    headers['Content-Type'] = 'application/json'
    
    req = urllib.request.Request(
        f"https://api-evm.orderly.org{path}",
        method="POST",
        headers=headers,
        data=body_str.encode()
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"Withdrawal failed: {e.code} - {error_body}")


def get_usdc_balance(w3, wallet_address):
    """Get USDC balance on Arbitrum"""
    # USDC ABI (just balanceOf)
    abi = [{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=abi)
    balance = usdc.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
    return balance / 1_000_000  # USDC has 6 decimals


def deposit_to_orderly(w3, wallet_private_key, amount_usdc, broker_id="arthur"):
    """Deposit USDC to Orderly vault for specified broker"""
    account = Account.from_key(wallet_private_key)
    wallet_address = account.address
    
    amount_raw = int(amount_usdc * 1_000_000)
    
    # Check USDC balance
    balance = get_usdc_balance(w3, wallet_address)
    print(f"  Wallet USDC balance: {balance:.2f}")
    
    if balance < amount_usdc:
        raise Exception(f"Insufficient USDC balance: {balance} < {amount_usdc}")
    
    # USDC ABI for approve
    usdc_abi = [
        {"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=usdc_abi)
    
    # Check current allowance
    allowance = usdc.functions.allowance(
        Web3.to_checksum_address(wallet_address),
        Web3.to_checksum_address(ORDERLY_VAULT)
    ).call()
    
    if allowance < amount_raw:
        print(f"  Approving USDC spend...")
        nonce = w3.eth.get_transaction_count(wallet_address)
        
        approve_tx = usdc.functions.approve(
            Web3.to_checksum_address(ORDERLY_VAULT),
            amount_raw
        ).build_transaction({
            'from': wallet_address,
            'nonce': nonce,
            'gas': 100000,
            'maxFeePerGas': w3.eth.gas_price * 2,
            'maxPriorityFeePerGas': w3.to_wei(0.01, 'gwei'),
        })
        
        signed_tx = w3.eth.account.sign_transaction(approve_tx, wallet_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"  Approve tx: {tx_hash.hex()}")
        
        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt['status'] != 1:
            raise Exception("Approve transaction failed")
        print(f"  Approve confirmed!")
    
    # Orderly Vault deposit ABI
    vault_abi = [
        {
            "inputs": [
                {"name": "accountId", "type": "bytes32"},
                {"name": "brokerHash", "type": "bytes32"},
                {"name": "tokenHash", "type": "bytes32"},
                {"name": "tokenAmount", "type": "uint128"}
            ],
            "name": "deposit",
            "outputs": [],
            "stateMutability": "payable",
            "type": "function"
        }
    ]
    vault = w3.eth.contract(address=Web3.to_checksum_address(ORDERLY_VAULT), abi=vault_abi)
    
    # Calculate hashes
    # Account ID is keccak256(abi.encodePacked(address, brokerId))
    from eth_abi import encode
    account_id = Web3.keccak(
        encode(['address', 'bytes32'], [
            Web3.to_checksum_address(wallet_address),
            Web3.keccak(text=broker_id)
        ])
    )
    
    broker_hash = Web3.keccak(text=broker_id)
    token_hash = Web3.keccak(text="USDC")
    
    print(f"  Depositing {amount_usdc} USDC to {broker_id} broker...")
    print(f"  Account ID: {account_id.hex()}")
    
    nonce = w3.eth.get_transaction_count(wallet_address)
    
    deposit_tx = vault.functions.deposit(
        account_id,
        broker_hash,
        token_hash,
        amount_raw
    ).build_transaction({
        'from': wallet_address,
        'nonce': nonce,
        'gas': 300000,
        'maxFeePerGas': w3.eth.gas_price * 2,
        'maxPriorityFeePerGas': w3.to_wei(0.01, 'gwei'),
        'value': 0
    })
    
    signed_tx = w3.eth.account.sign_transaction(deposit_tx, wallet_private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"  Deposit tx: {tx_hash.hex()}")
    
    # Wait for confirmation
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt['status'] != 1:
        raise Exception("Deposit transaction failed")
    
    print(f"  Deposit confirmed!")
    return tx_hash.hex()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate funds from Orderly to Arthur broker")
    parser.add_argument("--amount", type=float, required=True, help="Amount of USDC to migrate")
    parser.add_argument("--withdraw-only", action="store_true", help="Only withdraw, don't deposit")
    parser.add_argument("--deposit-only", action="store_true", help="Only deposit (assumes USDC in wallet)")
    args = parser.parse_args()
    
    # Load credentials
    orderly_creds = load_json("~/clawd/secrets/randy-orderly.json")
    wallet_creds = load_json("~/clawd/secrets/arthur-trading.json")
    
    wallet_address = wallet_creds['address']
    private_key = wallet_creds['privateKey']
    
    print(f"=== Migrating {args.amount} USDC from Orderly → Arthur ===")
    print(f"Wallet: {wallet_address}")
    
    w3 = Web3(Web3.HTTPProvider(ARBITRUM_RPC))
    if not w3.is_connected():
        raise Exception("Failed to connect to Arbitrum RPC")
    
    print(f"Connected to Arbitrum (block {w3.eth.block_number})")
    
    # Check ETH balance for gas
    eth_balance = w3.eth.get_balance(wallet_address)
    print(f"ETH balance: {w3.from_wei(eth_balance, 'ether'):.6f} ETH")
    
    if eth_balance < w3.to_wei(0.001, 'ether'):
        raise Exception("Insufficient ETH for gas")
    
    if not args.deposit_only:
        # Step 1: Withdraw from Orderly broker
        print("\n[1/2] Withdrawing from Orderly broker...")
        try:
            result = create_withdrawal_request(
                api_key=orderly_creds['key'],
                secret_key=orderly_creds['secret_key'],
                account_id=orderly_creds['account_id'],
                wallet_private_key=private_key,
                amount_usdc=args.amount,
                broker_id="orderly"
            )
            print(f"  Withdrawal result: {result}")
            
            if result.get('success'):
                print("  ✅ Withdrawal request submitted!")
                print("  Waiting for on-chain settlement (this can take 1-30 minutes)...")
                
                # Poll for USDC balance increase
                initial_balance = get_usdc_balance(w3, wallet_address)
                print(f"  Initial wallet USDC: {initial_balance:.2f}")
                
                for i in range(60):  # Wait up to 30 minutes
                    time.sleep(30)
                    current_balance = get_usdc_balance(w3, wallet_address)
                    if current_balance > initial_balance + (args.amount * 0.9):
                        print(f"  ✅ Withdrawal received! Balance: {current_balance:.2f}")
                        break
                    print(f"  ... waiting ({i+1}/60) - balance: {current_balance:.2f}")
                else:
                    print("  ⚠️ Withdrawal taking longer than expected. Check manually.")
                    if args.withdraw_only:
                        return
            else:
                print(f"  ❌ Withdrawal failed: {result}")
                return
        except Exception as e:
            print(f"  ❌ Withdrawal error: {e}")
            return
    
    if args.withdraw_only:
        print("\n✅ Withdrawal complete (--withdraw-only)")
        return
    
    # Step 2: Deposit to Arthur broker
    print("\n[2/2] Depositing to Arthur broker...")
    try:
        tx_hash = deposit_to_orderly(w3, private_key, args.amount, broker_id="arthur")
        print(f"  ✅ Deposit complete! TX: {tx_hash}")
    except Exception as e:
        print(f"  ❌ Deposit error: {e}")
        return
    
    print("\n=== Migration complete! ===")
    print(f"Migrated {args.amount} USDC from Orderly → Arthur broker")


if __name__ == "__main__":
    main()
