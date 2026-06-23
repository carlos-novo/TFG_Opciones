import asyncio
from ib_insync import IB

async def main():
    ib = IB()
    try:
        await ib.connectAsync('127.0.0.1', 4002, clientId=111)
        print("Conectado con éxito a IBKR.")
        print(f"Managed Accounts: {ib.managedAccounts()}")
        print(f"Account values count: {len(ib.accountValues())}")
        for val in ib.accountValues()[:20]:
            print(f"  - {val.tag}: {val.value} ({val.account})")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
