``` bash
python scripts/oef/launch.py -c ./scripts/oef/launch_config.json
```
``` bash
aea create erc1155_deployer
cd erc1155_deployer
aea add connection fetchai/oef:0.3.0
aea add skill fetchai/erc1155_deploy:0.4.0
aea install
aea config set agent.default_connection fetchai/oef:0.3.0
```
``` bash
aea generate-key ethereum
aea add-key ethereum eth_private_key.txt
```
``` bash
aea create erc1155_client
cd erc1155_client
aea add connection fetchai/oef:0.3.0
aea add skill fetchai/erc1155_client:0.3.0
aea install
aea config set agent.default_connection fetchai/oef:0.3.0
```
``` bash
aea generate-key ethereum
aea add-key ethereum eth_private_key.txt
```
``` bash
aea config set agent.default_ledger ethereum
```
``` bash
aea generate-wealth ethereum
```
``` bash
aea get-wealth ethereum
```
``` bash
aea run --connections fetchai/oef:0.3.0
```
``` bash
Successfully minted items. Transaction digest: ...
```
``` bash
aea run --connections fetchai/oef:0.3.0
```
``` bash
cd ..
aea delete erc1155_deployer
aea delete erc1155_client
```
``` yaml
ledger_apis:
  ethereum:
    address: https://ropsten.infura.io/v3/f00f7b3ba0e848ddbdc8941c527447fe
    chain_id: 3
    gas_price: 50
```
