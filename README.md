# SubSeaPro
A CLI queuing system for running calculations in AMPL on a remote server


## Installation

SSP uses a server-client infrastructure-, and requires installation on both systems.

### Client
Install using `pip install git+https://github.com/simon-ball/SubSeaPro`
Provide correct server_secrets:
* Rename `server_secrets.py.example` to `server_secrets.py`
* Enter the correct host address
* Enter the correct user name and path to private RSA key
* Enter correct username and password for access to the job queue

