# cs3103-assignment4
CS3103 Assignment 4

## Before Running
Self generate a cert.pem and key.pem in the project directory by running this command:
```bash
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj "/CN=localhost"
```

## To Run Client 
```bash
python test_client.py --host 127.0.0.1 --port 8001 --cert mycert.pem --key mykey.pem

python test_client.py --channel-id reliable --packet-count 5 --interval 0.2

python test_client.py --channel-id 1 --packet-count 20
```

## To Run Server
```bash
python server.py
```