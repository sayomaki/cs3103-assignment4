# cs3103-assignment4
CS3103 Assignment 4

## Before Running
Self generate a cert.pem and key.pem in the project directory by running this command:
```bash
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj "/CN=localhost"
```

## To Run Client 
```bash
python client.py --target 127.0.0.1:8001 --pps 10 --duration 10 --rel-ratio 0.5
```

## To Run Server
```bash
python server.py
```